"""Run SAMS over HTTPS/TLS with a self-signed dev certificate (SAM-SR-001).

Usage:  python run_https.py   ->   https://127.0.0.1:8443
The browser warns about the self-signed cert: click Advanced -> Proceed (dev only).
In production, terminate TLS at a reverse proxy (nginx/Caddy) with a real certificate.
"""
import datetime, ipaddress, os

import uvicorn

CERT_DIR = "certs"
CERT, KEY = os.path.join(CERT_DIR, "dev-cert.pem"), os.path.join(CERT_DIR, "dev-key.pem")


def make_cert():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    os.makedirs(CERT_DIR, exist_ok=True)
    with open(KEY, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


if __name__ == "__main__":
    if not (os.path.exists(CERT) and os.path.exists(KEY)):
        make_cert()
    print("Serving on https://127.0.0.1:8443")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8443, ssl_keyfile=KEY, ssl_certfile=CERT)
