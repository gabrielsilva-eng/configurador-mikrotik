# -*- coding: utf-8 -*-
"""
Configurador MikroTik - primeira versão
Gera scripts RouterOS 6/7 e pacote de certificado .p12.
Não conecta diretamente ao roteador nesta versão.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import re
import shutil
import ipaddress
import datetime

APP_TITLE = "Configurador MikroTik"
VPN_HOST = "awsatende.dyndns.org"
VPN_PORT = "1194"

def ros_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

def validate_prefix(value: str) -> str:
    value = value.strip()
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError("Informe os três primeiros octetos, por exemplo: 10.103.254")
    nums = [int(p) for p in parts]
    if any(n < 0 or n > 255 for n in nums):
        raise ValueError("Cada octeto precisa estar entre 0 e 255.")
    net = ipaddress.ip_network(value + ".0/24", strict=False)
    if net.network_address.packed[0] == 127 or net.network_address.is_multicast:
        raise ValueError("Essa faixa não é adequada para a LAN.")
    return ".".join(str(n) for n in nums)

def make_script(condo, prefix, cert_name, ros_version):
    # Mantém a lógica do script original enviado pelo usuário.
    # Netwatch sem type=icmp para maior compatibilidade com RouterOS 6/7.
    qcondo = condo.replace("\r", " ").replace("\n", " ").strip()
    lines = [
        "# ============================================================",
        f"# Configuracao MikroTik - {qcondo}",
        f"# Gerado em {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"# Perfil: RouterOS {ros_version}",
        "# ATENCAO: aplicar somente em equipamento zerado/factory reset.",
        "# ============================================================",
        "",
        f':global lanPrefix "{prefix}"',
        f':global vpnName "ORACLE"',
        f':global vpnHost "{VPN_HOST}"',
        f':global vpnPort "{VPN_PORT}"',
        f':global vpnCertName "{cert_name}"',
        "",
        "/interface list",
        "add name=WAN",
        "add name=LAN",
        "",
        "/interface bridge",
        "add name=bridge-LAN",
        "/interface bridge port",
        "add bridge=bridge-LAN interface=ether3",
        "add bridge=bridge-LAN interface=ether4",
        "add bridge=bridge-LAN interface=ether5",
        "",
        "/interface list member",
        "add list=WAN interface=ether1",
        "add list=WAN interface=ether2",
        "add list=LAN interface=bridge-LAN",
        "",
        "/ip address",
        'add address=($lanPrefix . ".1/24") network=($lanPrefix . ".0") interface=bridge-LAN comment="LAN"',
        "",
        "/ip dns",
        "set servers=8.8.8.8,8.8.4.4,1.1.1.1 allow-remote-requests=yes",
        "",
        "/ip pool",
        'add name=pool-lan ranges=($lanPrefix . ".2-" . $lanPrefix . ".254")',
        "/ip dhcp-server",
        "add name=dhcp-lan interface=bridge-LAN address-pool=pool-lan disabled=no",
        "/ip dhcp-server network",
        'add address=($lanPrefix . ".0/24") gateway=($lanPrefix . ".1") dns-server=($lanPrefix . ".1,1.1.1.1")',
        "",
        "/ip dhcp-client",
        'add comment=LINK_01 interface=ether1 add-default-route=no use-peer-dns=no use-peer-ntp=no disabled=no script=":local rota \\"ROTA_LINK_01\\"; :local monitor \\"ROTA_MONIT_LINK_01\\"; :if ($bound = 1) do={ :local gw $\\"gateway-address\\"; :log info (\\"Gateway recebido Link1: \\" . $gw); /ip route set [find where comment=$rota] gateway=$gw; /ip route set [find where comment=$monitor] gateway=$gw }"',
        'add comment=LINK_02 interface=ether2 add-default-route=no use-peer-dns=no use-peer-ntp=no disabled=no script=":local rota \\"ROTA_LINK_02\\"; :local monitor \\"ROTA_MONIT_LINK_02\\"; :if ($bound = 1) do={ :local gw $\\"gateway-address\\"; :log info (\\"Gateway recebido Link2: \\" . $gw); /ip route set [find where comment=$rota] gateway=$gw; /ip route set [find where comment=$monitor] gateway=$gw }"',
        "",
        "/ip route",
        "add comment=ROTA_LINK_01 dst-address=0.0.0.0/0 gateway=123.123.123.123 distance=1",
        "add comment=ROTA_LINK_02 dst-address=0.0.0.0/0 gateway=123.123.123.124 distance=2",
        "add comment=ROTA_MONIT_LINK_01 dst-address=8.8.8.8/32 gateway=123.123.123.123 distance=1",
        "add comment=ROTA_MONIT_LINK_02 dst-address=8.8.4.4/32 gateway=123.123.123.124 distance=2",
        "",
        "/tool netwatch",
        'add comment=MONIT_LINK01 host=8.8.8.8 interval=10s timeout=5s up-script=":local rota \\"ROTA_LINK_01\\"; :log info (\\"Habilitando \\" . $rota); /ip route enable [find where comment=$rota]" down-script=":local rota \\"ROTA_LINK_01\\"; :log warning (\\"Desabilitando \\" . $rota); /ip route disable [find where comment=$rota]"',
        'add comment=MONIT_LINK02 host=8.8.4.4 interval=10s timeout=5s up-script=":local rota \\"ROTA_LINK_02\\"; :log info (\\"Habilitando \\" . $rota); /ip route enable [find where comment=$rota]" down-script=":local rota \\"ROTA_LINK_02\\"; :log warning (\\"Desabilitando \\" . $rota); /ip route disable [find where comment=$rota]"',
        "",
        "/ip firewall address-list",
        "add list=Redes_Atende address=10.0.0.0/23",
        "add list=Redes_Atende address=10.32.30.144/28",
        "",
        "/ip firewall nat",
        'add chain=srcnat action=accept src-address-list=Redes_Atende comment="Nao faz NAT (origem)"',
        'add chain=srcnat action=accept dst-address-list=Redes_Atende comment="Nao faz NAT (destino)"',
        "add chain=srcnat action=masquerade out-interface-list=WAN comment=MASCARADE",
        "",
        "/ip firewall filter",
        'add chain=output dst-address=8.8.8.8 out-interface=ether2 protocol=icmp action=drop comment="Monit: 8.8.8.8 nao pinga pelo link 2"',
        'add chain=output dst-address=8.8.4.4 out-interface=ether1 protocol=icmp action=drop comment="Monit: 8.8.4.4 nao pinga pelo link 1"',
        'add chain=input src-address-list=Redes_Atende connection-state=new action=accept comment="Permitir acesso VPN"',
        'add chain=input protocol=icmp connection-state=new action=accept comment="Permitir ICMP"',
        'add chain=input in-interface-list=LAN connection-state=new action=accept comment="Permitir acesso LAN"',
        'add chain=input connection-state=established,related action=accept comment="Permitir relacionadas"',
        'add chain=input action=drop comment="Bloquear tudo (input)"',
        'add chain=forward in-interface-list=LAN out-interface-list=WAN connection-state=new action=accept comment="Permitir navegacao"',
        'add chain=forward src-address-list=Redes_Atende out-interface-list=LAN connection-state=new action=accept comment="Permitir VPN -> LAN"',
        'add chain=forward dst-address-list=Redes_Atende in-interface-list=LAN connection-state=new action=accept comment="Permitir LAN -> VPN"',
        'add chain=forward connection-state=new connection-nat-state=dstnat action=accept comment="Permitir dstnat"',
        'add chain=forward connection-state=established,related action=accept comment="Permitir estabelecidas e relacionadas"',
        'add chain=forward action=drop comment="Bloquear tudo (forward)"',
        "",
        "# Certificado .p12: importar primeiro pelo Winbox em System > Certificates.",
        f"# Renomeie o certificado importado para: {cert_name}",
        "# A senha do .p12 NAO e gravada neste script.",
        "",
        "/interface ovpn-client",
        f'add name=ORACLE comment="ORACLE_VPN" connect-to={VPN_HOST} port={VPN_PORT} user=any certificate={cert_name} cipher=aes128-cbc auth=sha1 add-default-route=no disabled=no',
        "",
        f':log info "Configuracao {qcondo} aplicada. Verifique a VPN."',
        "",
    ]
    return "\n".join(lines)

def make_readme(condo, prefix, cert_file, cert_name, versions):
    return f"""CONFIGURADOR MIKROTIK - PACOTE GERADO

Condominio: {condo}
LAN: {prefix}.0/24
Gateway LAN: {prefix}.1
Servidor VPN: {VPN_HOST}:{VPN_PORT}
Certificado: {cert_file}
Nome esperado no RouterOS: {cert_name}
Scripts gerados: {", ".join(versions)}

IMPORTANTE
- Este pacote foi gerado a partir do script-base fornecido.
- Destina-se a MikroTik zerado ou restaurado para configuracao de fabrica.
- NAO aplique em roteador em producao ou com configuracao existente sem revisao.
- A senha do .p12 nao e salva no pacote nem no historico.
- O arquivo .p12 contem material criptografico privado. Proteja esta pasta.

PASSOS MANUAIS
1. Conecte ao MikroTik pelo Winbox usando o MAC.
2. Confirme a versao do RouterOS e escolha o .rsc correspondente.
3. Envie o arquivo .p12 para Files no Winbox.
4. Em System > Certificates, importe o .p12 e informe a senha do certificado.
5. Renomeie o certificado que possui chave privada para: {cert_name}
6. Envie o script .rsc para Files.
7. Abra New Terminal e execute: /import file-name=NOME_DO_SCRIPT.rsc
8. Confira IP, DHCP, rotas, firewall e estado do cliente OVPN.

LIMITACOES DESTA VERSAO
- Nao conecta nem configura o roteador automaticamente.
- A identificacao da versao ainda e feita por voce no Winbox; o pacote pode conter
  scripts separados para RouterOS 6 e 7.
- A compatibilidade do OpenVPN depende tambem dos parametros do servidor.
- O script original foi descrito como RouterOS 7; a variante RouterOS 6 precisa
  ser validada em equipamento de teste antes de uso em producao.
- O script mantem as redes centrais Redes_Atende 10.0.0.0/23 e 10.32.30.144/28.
  Altere-as no codigo-fonte se os enderecos centrais mudarem.

Gerado em: {datetime.datetime.now():%Y-%m-%d %H:%M}
"""

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x820")
        self.minsize(760, 680)
        self.configure(bg="#101010")
        self.cert_path = tk.StringVar()
        self.condo = tk.StringVar()
        self.prefix = tk.StringVar(value="10.103.254")
        self.cert_name = tk.StringVar(value="ORACLE_CERT")
        self.version = tk.StringVar(value="Ambos (RouterOS 6 e 7)")
        self._build_styles()
        self._build_ui()

    def _build_styles(self):
        style = ttk.Style(self)
        # O tema clam respeita melhor as cores e evita fundos brancos inesperados
        # que aparecem em alguns controles no tema nativo do Windows.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.colors = {
            "bg": "#101010",
            "panel": "#1b1b1b",
            "text": "#f2f2f2",
            "muted": "#b8b8b8",
            "blue": "#d71920",
            "blue_light": "#351416",
            "border": "#3b3b3b",
        }
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"])
        style.configure("TLabel", background=self.colors["bg"],
                        foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.colors["bg"],
                        foreground="#ff3038", font=("Segoe UI", 23, "bold"))
        style.configure("Sub.TLabel", background=self.colors["bg"],
                        foreground=self.colors["muted"], font=("Segoe UI", 10))
        style.configure("Field.TLabel", background=self.colors["panel"],
                        foreground=self.colors["text"], font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#252525", foreground="#f5f5f5",
                        insertcolor="#ffffff", padding=(9, 8), font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground="#252525", background="#252525",
                        foreground="#f5f5f5", arrowcolor="#ff3038",
                        padding=(8, 7), font=("Segoe UI", 10))
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#252525")],
                  foreground=[("readonly", "#f5f5f5")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 9),
                        background="#303030", foreground="#f5f5f5")
        style.map("TButton", background=[("active", "#444444")])
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"),
                        padding=(16, 11), foreground="#ffffff",
                        background=self.colors["blue"])
        style.map("Accent.TButton",
                  background=[("active", "#f02a32"), ("pressed", "#a90f16")],
                  foreground=[("disabled", "#aaaaaa")])
        style.configure("TLabelframe", background=self.colors["panel"],
                        bordercolor=self.colors["border"])
        style.configure("TLabelframe.Label", background=self.colors["panel"],
                        foreground="#ff3038", font=("Segoe UI", 11, "bold"))
        style.configure("TSeparator", background="#454545")

    def _build_ui(self):
        # Área rolável: em telas menores, nenhum campo fica escondido.
        shell = ttk.Frame(self, style="App.TFrame")
        shell.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(shell, bg=self.colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self.canvas, style="App.TFrame", padding=(28, 24, 28, 28))
        self.content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content)
        self.bind_all("<MouseWheel>", self._mousewheel)

        ttk.Label(self.content, text="Configurador MikroTik",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.content,
            text="Gere os arquivos de configuração para cada novo condomínio.",
            style="Sub.TLabel"
        ).pack(anchor="w", pady=(5, 22))

        form = ttk.LabelFrame(self.content, text="Dados do condomínio", padding=18)
        form.pack(fill="x", pady=(0, 16))
        form.columnconfigure(0, weight=1)

        self._add_field(form, "Nome / identificação do condomínio", self.condo, 0)
        self._add_field(form, "Prefixo da rede LAN (ex.: 10.103.254)", self.prefix, 2)
        self._add_field(form, "Nome do certificado no MikroTik", self.cert_name, 4)

        ttk.Label(form, text="Arquivo do certificado (.p12)",
                  style="Field.TLabel").grid(row=6, column=0, sticky="w", pady=(13, 6))
        file_row = ttk.Frame(form, style="Panel.TFrame")
        file_row.grid(row=7, column=0, sticky="ew")
        file_row.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.cert_path).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(file_row, text="Selecionar arquivo...",
                   command=self.pick_cert).grid(row=0, column=1, padx=(10, 0))

        ttk.Label(form, text="Versão do RouterOS para gerar",
                  style="Field.TLabel").grid(row=8, column=0, sticky="w", pady=(15, 6))
        ttk.Combobox(
            form, textvariable=self.version, state="readonly",
            values=["Ambos (RouterOS 6 e 7)", "RouterOS 6", "RouterOS 7"]
        ).grid(row=9, column=0, sticky="ew")

        info = tk.Label(
            self.content,
            text=("A senha do certificado não é solicitada nem armazenada nesta etapa. "
                  "Ela será informada no Winbox durante a importação do .p12."),
            bg=self.colors["blue_light"], fg="#ffb7ba",
            justify="left", wraplength=780, padx=16, pady=14,
            font=("Segoe UI", 9)
        )
        info.pack(fill="x", pady=(0, 18))

        actions = ttk.Frame(self.content, style="App.TFrame")
        actions.pack(fill="x", pady=(0, 18))
        ttk.Button(
            actions, text="Gerar pacote de configuração",
            style="Accent.TButton", command=self.generate
        ).pack(side="right")

        ttk.Separator(self.content).pack(fill="x", pady=(0, 16))
        ttk.Label(
            self.content,
            text=("O pacote contém os scripts .rsc, o certificado selecionado e um "
                  "LEIA-ME com os passos de importação. A aplicação no roteador "
                  "ainda é manual nesta versão."),
            style="Sub.TLabel", wraplength=800, justify="left"
        ).pack(anchor="w")
        ttk.Label(
            self.content,
            text="Versão inicial • Configuração baseada no mikrotik-config.rsc fornecido",
            style="Sub.TLabel"
        ).pack(anchor="w", pady=(14, 0))

    def _add_field(self, parent, label, variable, row):
        ttk.Label(parent, text=label, style="Field.TLabel").grid(
            row=row, column=0, sticky="w", pady=(5, 6)
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row + 1, column=0, sticky="ew"
        )

    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content(self, event):
        self.canvas.itemconfigure(self.content_window, width=event.width)

    def _mousewheel(self, event):
        # Rolagem somente quando o cursor está sobre a janela do aplicativo.
        if self.winfo_containing(event.x_root, event.y_root) is not None:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def pick_cert(self):
        path = filedialog.askopenfilename(
            title="Selecione o certificado PKCS#12",
            filetypes=[("Certificado PKCS#12", "*.p12 *.pfx"),
                       ("Todos os arquivos", "*.*")]
        )
        if path:
            self.cert_path.set(path)

    def generate(self):
        condo = self.condo.get().strip()
        cert = Path(self.cert_path.get()) if self.cert_path.get() else None
        cert_name = self.cert_name.get().strip()
        try:
            prefix = validate_prefix(self.prefix.get())
            if not condo:
                raise ValueError("Informe o nome do condomínio.")
            if not cert or not cert.is_file():
                raise ValueError("Selecione um arquivo .p12 válido.")
            if cert.suffix.lower() not in (".p12", ".pfx"):
                raise ValueError("O certificado precisa ser .p12 ou .pfx.")
            if not cert_name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", cert_name):
                raise ValueError("Use um nome de certificado simples (letras, números, _, . ou -).")
        except Exception as e:
            messagebox.showerror("Verifique os dados", str(e))
            return

        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", condo).strip("_") or "Condominio"
        dest = filedialog.askdirectory(title="Escolha onde salvar o pacote")
        if not dest:
            return
        folder = Path(dest) / f"MikroTik_{safe_name}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            cert_dest = folder / cert.name
            if cert.resolve() != cert_dest.resolve():
                shutil.copy2(cert, cert_dest)
            versions = []
            choice = self.version.get()
            if choice.startswith("Ambos"):
                versions = ["6", "7"]
            elif "6" in choice:
                versions = ["6"]
            else:
                versions = ["7"]
            for v in versions:
                script = make_script(condo, prefix, cert_name, v)
                (folder / f"config-routeros{v}.rsc").write_text(script, encoding="utf-8")
            readme = make_readme(condo, prefix, cert.name, cert_name, versions)
            (folder / "LEIA-ME.txt").write_text(readme, encoding="utf-8")
            messagebox.showinfo("Pacote criado", f"Pacote salvo em:\n{folder}")
        except Exception as e:
            messagebox.showerror("Erro ao gerar", str(e))

if __name__ == "__main__":
    App().mainloop()
