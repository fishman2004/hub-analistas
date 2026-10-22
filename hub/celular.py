"""Abrir o Hub no celular pela Wi-Fi da empresa (fase 18): o endereço do PC da sala para o QR Code."""

import ipaddress
import socket

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")


def lan_ip() -> str | None:
    """O endereço deste PC na rede da empresa (ex.: 192.168.0.15), ou None se não achar.

    O "connect" de UDP não manda nada pela rede: só faz o Windows escolher a placa de rede de saída.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


def is_local(host: str) -> bool:
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if name in LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(name.strip("[]")).is_loopback
    except ValueError:
        return False


def phone_address(request_host: str, port: int, found_ip: str | None) -> str | None:
    """O endereço para o celular abrir.

    Quem abriu o Hub por um endereço da rede (no PC dele) já tem o endereço certo. Quem está no próprio
    PC da sala (127.0.0.1) usa o endereço da rede que o Windows informar. O nome do PC (http://PC-SALA:8800)
    funciona nos PCs, mas muitos celulares não acham nomes de PC Windows: por isso, sempre que dá, o número.
    """
    if request_host and not is_local(request_host):
        host = request_host
        name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        try:
            ipaddress.ip_address(name.strip("[]"))
        except ValueError:
            # abriu pelo nome do PC: troca pelo número, se o Windows souber
            if found_ip:
                return f"http://{found_ip}:{port}"
        return f"http://{host}"
    return f"http://{found_ip}:{port}" if found_ip else None
