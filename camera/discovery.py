"""Descubrimiento de cámaras ONVIF en la red local.

Implementa el protocolo WS-Discovery (multicast UDP 239.255.255.250:3702)
enviando un mensaje ``Probe`` y parseando las respuestas ``ProbeMatch``.
No depende de la clase WSDiscovery de onvif-zeep (poco fiable en
multicast) y funciona sin dependencias adicionales.
"""

from __future__ import annotations

import socket
import struct
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from utils.logger import get_logger

log = get_logger(__name__)

WS_DISCOVERY_ADDRESS = "239.255.255.250"
WS_DISCOVERY_PORT = 3702
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
DISCOVERY_NS = "http://schemas.xmlsoap.org/ws/2005/04/discovery"

PROBE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{soap}" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="{discovery}">
  <s:Header>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  </s:Header>
  <s:Body>
    <d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe>
  </s:Body>
</s:Envelope>"""


@dataclass(frozen=True)
class DiscoveredDevice:
    """Dispositivo ONVIF encontrado en la red."""

    host: str
    port: int
    xaddrs: tuple[str, ...]
    scopes: tuple[str, ...]
    types: tuple[str, ...]

    @property
    def device_service_url(self) -> str:
        """Devuelve la URL del servicio Device si está disponible."""
        for addr in self.xaddrs:
            if "device_service" in addr:
                return addr
        return self.xaddrs[0] if self.xaddrs else ""


def discover_devices(
    timeout: float = 4.0,
    interface_ip: str = "",
) -> list[DiscoveredDevice]:
    """Busca cámaras ONVIF en la red local.

    Args:
        timeout: Segundos a esperar respuestas tras enviar el Probe.
        interface_ip: IP de la interfaz a usar (vacío = automático).

    Returns:
        Lista de dispositivos encontrados.
    """
    probe = PROBE_TEMPLATE.format(
        soap=SOAP_NS,
        discovery=DISCOVERY_NS,
        message_id=str(uuid.uuid4()),
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind((interface_ip, 0))
        sock.sendto(
            probe.encode("utf-8"),
            (WS_DISCOVERY_ADDRESS, WS_DISCOVERY_PORT),
        )
    except OSError as exc:
        sock.close()
        log.error("No se pudo enviar el Probe WS-Discovery: %s", exc)
        return []

    responses: list[str] = []
    try:
        while True:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                break
            except OSError:
                break
            text = data.decode("utf-8", errors="ignore")
            if "<" in text:
                responses.append(text)
    finally:
        sock.close()

    devices = _parse_responses(responses)
    log.info("Descubrimiento finalizado: %s cámaras encontradas", len(devices))
    return devices


def _parse_responses(responses: list[str]) -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    seen: set[str] = set()
    for text in responses:
        try:
            device = _parse_probe_match(text)
        except Exception:  # noqa: BLE001 - una respuesta corrupta no rompe el scan
            continue
        if device is None or device.host in seen:
            continue
        seen.add(device.host)
        devices.append(device)
    return devices


def _parse_probe_match(xml_text: str) -> DiscoveredDevice | None:
    root = ET.fromstring(xml_text)
    xaddrs: list[str] = []
    scopes: list[str] = []
    types: list[str] = []

    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag == "XAddrs" and elem.text:
            xaddrs = [a for a in elem.text.split() if a]
        elif tag == "Scopes" and elem.text:
            scopes = [s for s in elem.text.split() if s]
        elif tag == "Types" and elem.text:
            types = [t for t in elem.text.split() if t]

    if not xaddrs:
        return None

    host, port = _first_host(xaddrs)
    if not host:
        return None

    return DiscoveredDevice(
        host=host,
        port=port,
        xaddrs=tuple(xaddrs),
        scopes=tuple(scopes),
        types=tuple(types),
    )


def _first_host(xaddrs: list[str]) -> tuple[str, int]:
    for addr in xaddrs:
        parts = urlsplit(addr)
        if parts.hostname:
            return parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)
    return "", 0


def _local_name(tag: Any) -> str:
    name = str(tag)
    if "}" in name:
        return name.rsplit("}", 1)[1]
    return name
