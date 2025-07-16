import socket

def test_port(host, port):
    with socket.socket() as s:
        s.settimeout(3)
        try:
            s.connect((host, port))
            print(f"✅ Port {port} on {host} is open.")
        except:
            print(f"❌ Port {port} on {host} is closed or blocked.")

test_port("ulcdl-4F3MG04.abbvienet.com", 1183)
test_port("ulcdl-4F3MG04.abbvienet.com", 443)
