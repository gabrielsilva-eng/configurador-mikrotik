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
        self.geometry("720x600")
        self.minsize(680, 560)
        self.configure(bg="#f3f5f8")
        self.cert_path = tk.StringVar()
        self.condo = tk.StringVar()
        self.prefix = tk.StringVar(value="10.103.254")
        self.cert_name = tk.StringVar(value="ORACLE_CERT")
        self.version = tk.StringVar(value="Ambos (RouterOS 6 e 7)")
        self.build_ui()

    def build_ui(self):
        style = ttk.Style(self)
        try: style.theme_use("vista")
        except tk.TclError: pass
        style.configure("TLabel", background="#f3f5f8", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#14233b")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#526174")
        style.configure("TButton", font=("Segoe UI", 10), padding=8)
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=10)
        outer = ttk.Frame(self, padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Configurador MikroTik", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Gere os arquivos de configuração para cada novo condomínio.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2,18))
        form = ttk.Frame(outer)
        form.pack(fill="x")
        self.add_field(form, "Nome / identificação do condomínio", self.condo, 0)
        self.add_field(form, "Prefixo da rede LAN (ex.: 10.103.254)", self.prefix, 1)
        self.add_field(form, "Nome do certificado no MikroTik", self.cert_name, 2)
        ttk.Label(form, text="Arquivo do certificado (.p12)").grid(row=3, column=0, sticky="w", pady=(12,5))
        file_row = ttk.Frame(form)
        file_row.grid(row=4, column=0, sticky="ew")
        form.columnconfigure(0, weight=1)
        ttk.Entry(file_row, textvariable=self.cert_path).pack(side="left", fill="x", expand=True)
        ttk.Button(file_row, text="Selecionar...", command=self.pick_cert).pack(side="left", padx=(8,0))
        ttk.Label(form, text="Versão do RouterOS para gerar").grid(row=5, column=0, sticky="w", pady=(14,5))
        ttk.Combobox(form, textvariable=self.version, state="readonly",
                     values=["Ambos (RouterOS 6 e 7)", "RouterOS 6", "RouterOS 7"]).grid(row=6, column=0, sticky="ew")
        info = tk.Label(outer, text=("A senha do certificado não é solicitada nem armazenada nesta etapa. "
                                    "Ela será informada no Winbox durante a importação do .p12."),
                        bg="#eaf1fb", fg="#1d426f", justify="left", wraplength=640,
                        padx=12, pady=12, font=("Segoe UI", 9))
        info.pack(fill="x", pady=18)
        ttk.Button(outer, text="Gerar pacote de configuração", style="Accent.TButton",
                   command=self.generate).pack(anchor="e")
        ttk.Separator(outer).pack(fill="x", pady=18)
        ttk.Label(outer, text="O pacote contém o(s) script(s) .rsc, o certificado selecionado e um LEIA-ME "
                              "com os passos de importação. A aplicação no roteador ainda é manual nesta versão.",
                  style="Sub.TLabel", wraplength=650).pack(anchor="w")
        ttk.Label(outer, text="Versão inicial • Configuração baseada no mikrotik-config.rsc fornecido",
                  style="Sub.TLabel").pack(anchor="w", side="bottom", pady=(20,0))

    def add_field(self, parent, label, variable, row):
        ttk.Label(parent, text=label).grid(row=row*2, column=0, sticky="w", pady=(5,4))
        ttk.Entry(parent, textvariable=variable).grid(row=row*2+1, column=0, sticky="ew", pady=(0,5))

    def pick_cert(self):
        path = filedialog.askopenfilename(title="Selecione o certificado PKCS#12",
                                          filetypes=[("Certificado PKCS#12", "*.p12 *.pfx"), ("Todos os arquivos", "*.*")])
        if path: self.cert_path.set(path)

    def generate(self):
        condo = self.condo.get().strip()
        cert = Path(self.cert_path.get()) if self.cert_path.get() else None
        cert_name = self.cert_name.get().strip()
        try:
            prefix = validate_prefix(self.prefix.get())
            if not condo: raise ValueError("Informe o nome do condomínio.")
            if not cert or not cert.is_file(): raise ValueError("Selecione um arquivo .p12 válido.")
            if cert.suffix.lower() not in (".p12", ".pfx"): raise ValueError("O certificado precisa ser .p12 ou .pfx.")
            if not cert_name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", cert_name):
                raise ValueError("Use um nome de certificado simples (letras, números, _, . ou -).")
        except Exception as e:
            messagebox.showerror("Verifique os dados", str(e)); return

        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", condo).strip("_") or "Condominio"
        dest = filedialog.askdirectory(title="Escolha onde salvar o pacote")
        if not dest: return
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
