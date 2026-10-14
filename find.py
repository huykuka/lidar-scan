import socket
import concurrent.futures
import ipaddress

# --- CONFIGURATION ---
SEARCH_TIMEOUT = 0.3  # Timeout in seconds for socket connection and receive
MAX_WORKERS = 64      # Number of concurrent threads for rapid scanning
# ---------------------

def get_local_subnets():
    """
    Dynamically discovers all active IPv4 subnets across any OS (Windows, macOS, Linux)
    using standard Python socket APIs.
    """
    subnets = []
    seen_ips = set()
    
    # Method 1: Collect IPs via hostname resolution
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in seen_ips:
                seen_ips.add(ip)
                try:
                    network = ipaddress.ip_network(f"{ip}/24", strict=False)
                    subnets.append((ip, network))
                except Exception:
                    pass
    except Exception:
        pass

    # Method 2: Fallback / Supplement using the active outbound UDP route
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and not primary_ip.startswith("127.") and primary_ip not in seen_ips:
            seen_ips.add(primary_ip)
            network = ipaddress.ip_network(f"{primary_ip}/24", strict=False)
            subnets.append((primary_ip, network))
    except Exception:
        pass
        
    return subnets

def probe_sick_device(ip, port=2111, timeout=SEARCH_TIMEOUT):
    """Probes port 2111 and verifies if a valid DeviceIdent payload is returned."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.sendall(b'\x02sRN DeviceIdent\x03')
        resp = s.recv(256)
        if resp and b'DeviceIdent' in resp:
            return resp
    except (socket.timeout, ConnectionRefusedError, OSError):
        pass
    finally:
        s.close()
    return None

def scan_device_ip(ip):
    """Scans an IP address and returns it only if a valid DeviceIdent is found."""
    resp = probe_sick_device(ip)
    if resp:
        return str(ip), resp
    return None

def scan_network():
    local_subnets = get_local_subnets()
    if not local_subnets:
        print("[-] No active non-loopback network interfaces found.")
        return

    print(f"[*] Active local network interfaces:")
    for host_ip, net in local_subnets:
        print(f"    - Host IP: {host_ip} -> Subnet: {net}")
    print("\n" + "="*50 + "\n")

    all_ips_to_scan = []
    for host_ip, network in local_subnets:
        for ip in network.hosts():
            if str(ip) != host_ip:
                all_ips_to_scan.append(ip)

    print(f"Scanning {len(all_ips_to_scan)} total IPs (Search Timeout: {SEARCH_TIMEOUT}s)...\n")

    found_devices = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scan_device_ip, str(ip)): ip for ip in all_ips_to_scan}
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                ip, raw_resp = result
                decoded = raw_resp.decode('ascii', errors='ignore').strip()
                found_devices.append((ip, decoded))
                print(f"[+] IP: {ip:<15} | Identification: {decoded}")

    print(f"\nScan complete. Total SICK devices with DeviceIdent found: {len(found_devices)}")

if __name__ == "__main__":
    scan_network()