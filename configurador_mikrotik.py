# -*- coding: utf-8 -*-
"""
Configurador MikroTik
Gera scripts RouterOS 6/7 para LAN, DHCP, dual-WAN com failover,
firewall/NAT e um script separado para rotas das VPNs criadas manualmente.

ATENCAO:
- Aplicar inicialmente em roteador zerado ou apos backup e revisao.
- O script base nao cria clientes OVPN nem importa certificados.
- Depois de criar os clientes OVPN com os nomes ORACLE e UNDER,
  importar rotas-vpn.rsc.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import datetime
import ipaddress
import re

APP_TITLE = "Configurador MikroTik"
VPN_NETWORKS = {
    "ORACLE": "10.0.0.0/23",
    "UNDER": "10.32.30.144/28",
}
PROBE_1 = "1.1.1.1"
PROBE_2 = "8.8.4.4"


def validate_prefix(value: str) -> str:
    value = value.strip()
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError("Informe os tres primeiros octetos, por exemplo: 10.103.254")
    nums = [int(p) for p in parts]
    if any(n < 0 or n > 255 for n in nums):
        raise ValueError("Cada octeto precisa estar entre 0 e 255.")
    network = ipaddress.ip_network(value + ".0/24", strict=False)
    if network.network_address.is_loopback or network.network_address.is_multicast:
        raise ValueError("Essa faixa nao e adequada para a LAN.")
    for vpn_cidr in VPN_NETWORKS.values():
        if network.overlaps(ipaddress.ip_network(vpn_cidr)):
            raise ValueError(f"A faixa LAN nao pode sobrepor a rede VPN {vpn_cidr}.")
    return ".".join(str(n) for n in nums)


def ros_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dhcp_script(link: int) -> str:
    route = f"ROTA_LINK_0{link}"
    monitor = f"ROTA_MONIT_LINK_0{link}"
    script = (
        f':if ($bound = 1) do={{ '
        f':local gw $"gateway-address"; '
        f':log info ("Gateway recebido LINK_0{link}: " . $gw); '
        f'/ip route set [find where comment="{route}"] gateway=$gw disabled=no; '
        f'/ip route set [find where comment="{monitor}"] gateway=$gw disabled=no; '
        f'}} else={{ '
        f'/ip route disable [find where comment="{route}"]; '
        f'/ip route disable [find where comment="{monitor}"]; '
        f':log warning "LINK_0{link} sem concessao DHCP"; '
        f'}}'
    )
    return ros_quote(script)


def netwatch_script(link: int) -> tuple[str, str]:
    route = f"ROTA_LINK_0{link}"
    up = f':log info "LINK_0{link} disponivel"; /ip route enable [find where comment="{route}"]'
    down = f':log warning "LINK_0{link} indisponivel"; /ip route disable [find where comment="{route}"]'
    return ros_quote(up), ros_quote(down)


def make_base_script(condo: str, prefix: str, ros_version: str) -> str:
    safe_condo = condo.replace("\r", " ").replace("\n", " ").strip()
    lan_ip = f"{prefix}.1/24"
    lan_network = f"{prefix}.0/24"
    pool = f"{prefix}.10-{prefix}.254"
    dns = "8.8.8.8,8.8.4.4,1.1.1.1"
    up1, down1 = netwatch_script(1)
    up2, down2 = netwatch_script(2)

    lines = [
        "# ============================================================",
        f"# Configuracao MikroTik - {safe_condo}",
        f"# Gerado em {datetime.datetime.now():%Y-%m-%d %H:%M}",
        f"# Perfil: RouterOS {ros_version}",
        "# Aplicar em equipamento novo/zerado ou apos backup e revisao.",
        "# VPNs NAO sao criadas por este arquivo.",
        "# ============================================================",
        "",
        "# 1. LISTAS DE INTERFACES",
        "/interface list",
        "add name=WAN comment=LISTA_WAN",
        "add name=LAN comment=LISTA_LAN",
        "",
        "# 2. BRIDGE E PORTAS LAN",
        "/interface bridge",
        "add name=bridge-LAN protocol-mode=rstp comment=BRIDGE_LAN",
        "/interface bridge port",
        "add bridge=bridge-LAN interface=ether3",
        "add bridge=bridge-LAN interface=ether4",
        "add bridge=bridge-LAN interface=ether5",
        "",
        "# 3. MEMBROS DAS LISTAS",
        "/interface list member",
        "add list=WAN interface=ether1",
        "add list=WAN interface=ether2",
        "add list=LAN interface=bridge-LAN",
        "",
        "# 4. ENDERECO LAN",
        "/ip address",
        f"add address={lan_ip} network={prefix}.0 interface=bridge-LAN comment=LAN_CONDOMINIO",
        "",
        "# 5. DNS",
        "/ip dns",
        f"set servers={dns} allow-remote-requests=yes",
        "",
        "# 6. DHCP",
        "/ip pool",
        f"add name=pool-lan ranges={pool}",
        "/ip dhcp-server",
        "add name=dhcp-lan interface=bridge-LAN address-pool=pool-lan lease-time=1d disabled=no",
        "/ip dhcp-server network",
        f"add address={lan_network} gateway={prefix}.1 dns-server={prefix}.1,1.1.1.1",
        "",
        "# 7. DHCP CLIENTS WAN - ROTAS DEFAULT SAO CONTROLADAS PELOS SCRIPTS",
        "/ip dhcp-client",
        f"add interface=ether1 comment=LINK_01 add-default-route=no use-peer-dns=no use-peer-ntp=no disabled=no script={dhcp_script(1)}",
        f"add interface=ether2 comment=LINK_02 add-default-route=no use-peer-dns=no use-peer-ntp=no disabled=no script={dhcp_script(2)}",
        "",
        "# 8. ROTAS DEFAULT E ROTAS FIXAS DE MONITORAMENTO",
        "# Os gateways de exemplo serao substituidos pelos gateways DHCP.",
        "/ip route",
        "add dst-address=0.0.0.0/0 gateway=123.123.123.123 distance=1 comment=ROTA_LINK_01 disabled=yes",
        "add dst-address=0.0.0.0/0 gateway=123.123.123.124 distance=2 comment=ROTA_LINK_02 disabled=yes",
        f"add dst-address={PROBE_1}/32 gateway=123.123.123.123 distance=1 comment=ROTA_MONIT_LINK_01 disabled=yes",
        f"add dst-address={PROBE_2}/32 gateway=123.123.123.124 distance=1 comment=ROTA_MONIT_LINK_02 disabled=yes",
        "",
        "# 9. BLOQUEIA SONDAS DE MONITORAMENTO PELO LINK ERRADO",
        "/ip firewall filter",
        f"add chain=output dst-address={PROBE_1} out-interface=ether2 protocol=icmp action=drop comment=MONIT_NAO_SAIR_LINK_02",
        f"add chain=output dst-address={PROBE_2} out-interface=ether1 protocol=icmp action=drop comment=MONIT_NAO_SAIR_LINK_01",
        "",
        "# 10. NETWATCH - CADA HOST E FIXADO A UM LINK POR ROTA /32",
        "/tool netwatch",
        f"add host={PROBE_1} interval=10s timeout=5s up-script={up1} down-script={down1} comment=MONIT_LINK01",
        f"add host={PROBE_2} interval=10s timeout=5s up-script={up2} down-script={down2} comment=MONIT_LINK02",
        "",
        "# 11. REDES ATENDIDAS PELAS VPNs",
        "/ip firewall address-list",
        f"add list=Redes_Atende address={VPN_NETWORKS['ORACLE']} comment=REDE_ORACLE",
        f"add list=Redes_Atende address={VPN_NETWORKS['UNDER']} comment=REDE_UNDER",
        "",
        "# 12. NAT - NAO MASCARAR TRAFEGO DAS REDES VPN",
        "/ip firewall nat",
        'add chain=srcnat action=accept dst-address-list=Redes_Atende comment="NAO_NAT_DESTINO_VPN"',
        'add chain=srcnat action=accept src-address-list=Redes_Atende comment="NAO_NAT_ORIGEM_VPN"',
        'add chain=srcnat action=masquerade out-interface-list=WAN comment=MASCARADE_WAN',
        "",
        "# 13. FIREWALL INPUT - ACESSO AO PROPRIO MIKROTIK",
        "/ip firewall filter",
        'add chain=input connection-state=established,related action=accept comment=INPUT_ESTABLISHED_RELATED',
        'add chain=input connection-state=invalid action=drop comment=INPUT_INVALID_DROP',
        'add chain=input protocol=icmp action=accept comment=INPUT_ICMP',
        'add chain=input in-interface-list=LAN action=accept comment=INPUT_LAN',
        'add chain=input src-address-list=Redes_Atende action=accept comment=INPUT_REDES_VPN',
        'add chain=input action=drop comment=INPUT_DROP_RESTANTE',
        "",
        "# 14. FIREWALL FORWARD - TRAFEGO ATRAVES DO MIKROTIK",
        'add chain=forward connection-state=established,related action=accept comment=FORWARD_ESTABLISHED_RELATED',
        'add chain=forward connection-state=invalid action=drop comment=FORWARD_INVALID_DROP',
        'add chain=forward connection-nat-state=dstnat action=accept comment=FORWARD_DSTNAT',
        'add chain=forward in-interface-list=LAN dst-address-list=Redes_Atende action=accept comment=LAN_PARA_VPNS',
        'add chain=forward src-address-list=Redes_Atende out-interface-list=LAN action=accept comment=VPNS_PARA_LAN',
        'add chain=forward in-interface-list=LAN out-interface-list=WAN action=accept comment=LAN_PARA_INTERNET',
        'add chain=forward action=drop comment=FORWARD_DROP_RESTANTE',
        "",
        f':log info "Configuracao base de {safe_condo} importada. Configure as VPNs e importe rotas-vpn.rsc."',
        "",
    ]
    return "\n".join(lines)


def make_vpn_routes_script() -> str:
    return "\n".join([
        "# ROTAS DAS VPNs - IMPORTAR DEPOIS DE CRIAR OS CLIENTES OVPN",
        "# Nomes esperados das interfaces OVPN: ORACLE e UNDER.",
        "# Mapeamento adotado conforme as duas redes informadas no roteiro:",
        f"# ORACLE -> {VPN_NETWORKS['ORACLE']}",
        f"# UNDER  -> {VPN_NETWORKS['UNDER']}",
        "# Se a associacao estiver invertida, altere os gateways antes de importar.",
        "",
        "/ip route",
        f'add dst-address={VPN_NETWORKS["ORACLE"]} gateway=ORACLE comment=ROTA_REDE_ORACLE',
        f'add dst-address={VPN_NETWORKS["UNDER"]} gateway=UNDER comment=ROTA_REDE_UNDER',
        "",
        ':log info "Rotas das VPNs adicionadas. Teste os destinos remotos."',
        "",
    ])


def make_readme(condo: str, prefix: str, versions: list[str]) -> str:
    return f"""CONFIGURADOR MIKROTIK - PACOTE GERADO

Condominio: {condo}
LAN: {prefix}.0/24
Gateway LAN: {prefix}.1
Portas WAN: ether1 (principal), ether2 (secundaria)
Portas LAN: ether3, ether4, ether5 (bridge-LAN)
Versoes geradas: {", ".join("RouterOS " + v for v in versions)}

REDES VPN CONSIDERADAS
ORACLE: {VPN_NETWORKS["ORACLE"]}
UNDER:  {VPN_NETWORKS["UNDER"]}

ORDEM DE APLICACAO
1. Faça backup da configuracao atual do MikroTik.
2. Este pacote foi pensado para roteador zerado ou configuracao revisada.
3. Envie config-routerosX.rsc para Files e importe pelo Terminal:
   /import file-name=config-routerosX.rsc
4. Crie manualmente os clientes OVPN no Winbox:
   - Cliente ORACLE: interface com nome exatamente ORACLE.
   - Cliente UNDER: interface com nome exatamente UNDER.
   Configure certificados, servidor, porta, usuario e demais parametros de cada VPN.
5. Depois que as duas interfaces OVPN existirem, envie rotas-vpn.rsc para Files
   e importe:
   /import file-name=rotas-vpn.rsc
6. Verifique em IP > Routes se as duas rotas aparecem ativas.
7. Teste ping para um IP real de cada rede remota e teste um equipamento da LAN.

OBSERVACOES IMPORTANTES
- O programa NAO importa certificados e NAO cria os clientes OVPN.
- As redes VPN foram associadas por ordem, como hipotese:
  10.0.0.0/23 = ORACLE; 10.32.30.144/28 = UNDER.
  Confirme esse mapeamento antes de aplicar. Se estiver invertido, edite
  rotas-vpn.rsc antes da importacao.
- O failover usa sondas ICMP independentes (1.1.1.1 pelo LINK 01 e
  8.8.4.4 pelo LINK 02). Se a operadora bloquear ICMP, escolha hosts de teste
  que respondam a ping.
- O DHCP client precisa receber gateway via DHCP em cada WAN.
- A configuracao de firewall pressupoe que este roteador sera o gateway da LAN.
- O script base nao apaga configuracoes existentes. Em roteador ja configurado,
  regras, listas, bridges e DHCP duplicados podem conflitar.
- RouterOS 6 e 7 possuem diferencas entre versoes menores. Teste em equipamento
  de laboratorio antes de aplicar em producao.
- Nenhum script pode garantir acesso remoto sem os parametros corretos dos
  servidores VPN, certificados validos, rotas do lado remoto e liberacao de
  firewall no destino.

DIAGNOSTICO NO TERMINAL
/ip dhcp-client print detail
/ip route print detail
/tool netwatch print detail
/interface ovpn-client print detail
/ip firewall filter print
/ping 1.1.1.1
/ping 8.8.4.4

Gerado em: {datetime.datetime.now():%Y-%m-%d %H:%M}
"""


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("760x650")
        self.minsize(680, 580)
        self.configure(bg="#111111")
        self.condo = tk.StringVar()
        self.prefix = tk.StringVar(value="10.103.254")
        self.version = tk.StringVar(value="Ambos (RouterOS 6 e 7)")
        self._styles()
        self._build()

    def _styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        bg, panel = "#111111", "#1d1d1d"
        style.configure("App.TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground="#f2f2f2", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=bg, foreground="#ff3038", font=("Segoe UI", 22, "bold"))
        style.configure("Sub.TLabel", background=bg, foreground="#bbbbbb", font=("Segoe UI", 10))
        style.configure("Field.TLabel", background=panel, foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="#292929", foreground="#ffffff", insertcolor="#ffffff", padding=8)
        style.configure("TCombobox", fieldbackground="#292929", foreground="#ffffff", padding=7)
        style.configure("TButton", padding=(12, 9), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#d71920", foreground="#ffffff", padding=(16, 11), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#ef2b33")])
        style.configure("TLabelframe", background=panel, foreground="#ffffff")
        style.configure("TLabelframe.Label", background=panel, foreground="#ff3038", font=("Segoe UI", 11, "bold"))

    def _build(self):
        root = ttk.Frame(self, style="App.TFrame", padding=26)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="Configurador MikroTik", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Gere a configuracao de LAN, DHCP, dual-WAN, failover, NAT e firewall.",
                  style="Sub.TLabel", wraplength=680).pack(anchor="w", pady=(6, 20))

        form = ttk.LabelFrame(root, text="Dados do condominio", padding=18)
        form.pack(fill="x", pady=(0, 14))
        form.columnconfigure(0, weight=1)

        ttk.Label(form, text="Nome / identificacao do condominio", style="Field.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(form, textvariable=self.condo).grid(row=1, column=0, sticky="ew")

        ttk.Label(form, text="Prefixo da rede LAN (ex.: 10.103.254)", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 6))
        ttk.Entry(form, textvariable=self.prefix).grid(row=3, column=0, sticky="ew")

        ttk.Label(form, text="Versao do RouterOS", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=(14, 6))
        ttk.Combobox(form, textvariable=self.version, state="readonly",
                     values=["Ambos (RouterOS 6 e 7)", "RouterOS 6", "RouterOS 7"]).grid(row=5, column=0, sticky="ew")

        info = tk.Label(
            root,
            text=("VPNs e certificados ficam fora do programa. Crie ORACLE e UNDER manualmente "
                  "no Winbox; depois importe o arquivo separado de rotas VPN."),
            bg="#351416", fg="#ffc4c6", justify="left", wraplength=680,
            padx=14, pady=12, font=("Segoe UI", 9)
        )
        info.pack(fill="x", pady=(0, 14))

        actions = ttk.Frame(root, style="App.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Gerar pacote .RSC", style="Accent.TButton",
                   command=self.generate).pack(side="right")

        ttk.Label(
            root,
            text=("O pacote inclui scripts separados para RouterOS 6/7, rotas-vpn.rsc "
                  "e LEIA-ME.txt. As rotas VPN devem ser importadas somente depois "
                  "de criar os clientes OVPN com os nomes ORACLE e UNDER."),
            style="Sub.TLabel", wraplength=680, justify="left"
        ).pack(anchor="w", pady=(18, 0))

    def generate(self):
        condo = self.condo.get().strip()
        try:
            prefix = validate_prefix(self.prefix.get())
            if not condo:
                raise ValueError("Informe o nome ou identificacao do condominio.")
        except Exception as exc:
            messagebox.showerror("Verifique os dados", str(exc))
            return

        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", condo).strip("_") or "Condominio"
        destination = filedialog.askdirectory(title="Escolha onde salvar o pacote")
        if not destination:
            return

        versions = ["6", "7"] if self.version.get().startswith("Ambos") else (["6"] if "6" in self.version.get() else ["7"])
        folder = Path(destination) / f"MikroTik_{safe_name}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for version in versions:
                filename = folder / f"config-routeros{version}.rsc"
                filename.write_text(make_base_script(condo, prefix, version), encoding="utf-8")
            (folder / "rotas-vpn.rsc").write_text(make_vpn_routes_script(), encoding="utf-8")
            (folder / "LEIA-ME.txt").write_text(make_readme(condo, prefix, versions), encoding="utf-8")
            messagebox.showinfo("Pacote criado", f"Arquivos gerados em:\n{folder}")
        except Exception as exc:
            messagebox.showerror("Erro ao gerar", str(exc))


if __name__ == "__main__":
    App().mainloop()
