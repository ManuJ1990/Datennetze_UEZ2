import socket
import sys
import re


def parseUrl(url):
    # RegEx zum Parsen der URL
    url_regex = re.compile(
        r'^(http)://([^/:]+)(?::(\d+))?(.*)$'
    )
    match = url_regex.match(url)
    if not match:
        raise ValueError("Ungueltige URL.")

    # Extrahieren der einzelnen Teile der URL
    scheme = match.group(1)
    host = match.group(2)
    port = match.group(3)
    path = match.group(4)

    # Standard-Port auf 80 setzen, falls kein Port in der URL angegeben ist
    if not port:
        port = 80
    else:
        port = int(port)

    # Falls kein Pfad vorhanden ist, Standardwert '/' setzen
    if not path or path == '':
        path = '/'

    return scheme, host, path, port


def buildRequest(host, path):
    # Aufbau der ersten Zeile des HTTP-Requests (Request Line)
    requestLine = f"GET {path} HTTP/1.1\r\n"
    # Erstellen der HTTP-Header für den Request
    headers = [
        f"Host: {host}",
        "Connection: close",  # Verbindung schließen nach Beendigung der Anfrage
        "User-Agent: SimpleHTTPClient/1.0"  # Benutzerdefinierter User-Agent
    ]
    # Zusammenfügen der Header in eine Sektion
    headerSection = "\r\n".join(headers)
    # Vollständiger Request mit Request Line und Headern, abgeschlossen mit doppeltem CRLF
    fullRequest = requestLine + headerSection + "\r\n\r\n"

    return fullRequest


def sendRequest(host, port, request):
    # Socket für die Verbindung erstellen (IPv4, TCP)
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    clientSocket.settimeout(10)  # Timeout hinzufügen, um endloses Warten zu verhindern
    try:
        # Hostnamen auflösen in eine IP-Adresse
        ip = resolve_host(host)
        clientSocket.connect((ip, port))  # Verbindung zum Server herstellen

        # Senden der gesamten Anfrage an den Server
        clientSocket.sendall(request.encode())

        # Empfangen der Antwort vom Server
        response = b""
        while True:
            data = clientSocket.recv(4096)  # Daten in Blöcken von 4096 Bytes empfangen
            if not data:
                break  # Beenden, wenn keine weiteren Daten gesendet werden
            response += data
    except Exception as e:
        print(f"Fehler bei der Verbindung zum Server: {e}")
        clientSocket.close()
        sys.exit(1)
    finally:
        clientSocket.close()  # Socket schließen, nachdem die Antwort empfangen wurde

    return response


def parseResponse(response):
    # Finden der Grenze zwischen Header und Body (markiert das Ende des Headers)
    headerEndIndex = response.find(b"\r\n\r\n")
    if headerEndIndex == -1:
        raise ValueError("Ungueltige HTTP-Antwort: Kein Header Ende gefunden.")

    # Extrahieren des Headers und des Bodys aus der Antwort
    headerBytes = response[:headerEndIndex]
    bodyBytes = response[headerEndIndex + 4:]

    # Header in Text umwandeln (ISO-8859-1 für maximale Kompatibilität)
    headerText = headerBytes.decode('iso-8859-1')

    # Zerlegen der Header in einzelne Zeilen
    headerLines = headerText.split('\r\n')
    statusLine = headerLines[0]  # Erste Zeile ist die Statuszeile

    # Zerlegen der Statuszeile in HTTP-Version, Statuscode und Statusnachricht
    statusParts = statusLine.split(' ', 2)

    if len(statusParts) < 2:
        raise ValueError("Ungueltige Statuszeile in der HTTP-Antwort.")

    statusCode = int(statusParts[1])
    statusMessage = statusParts[2] if len(statusParts) > 2 else ''

    # Extrahieren der Header als Dictionary
    headers = {}
    for line in headerLines[1:]:
        if ': ' in line:
            key, value = line.split(': ', 1)
            headers[key.strip()] = value.strip()

    return statusCode, headers, bodyBytes, statusMessage


def resolve_host(host):
    try:
        # Auflösen des Hostnamens in eine IP-Adresse
        ip = socket.gethostbyname(host)
        return ip
    except socket.gaierror as e:
        raise Exception(f"Hostname konnte nicht aufgeloest werden: {e}")


def resolve_redirect_url(base_url, location):
    # Vollständige URL, falls der Location-Header bereits eine absolute URL enthält
    if location.startswith('http://'):
        return location
    elif location.startswith('/'):
        # Hostteil der Basis-URL extrahieren, um die Umleitung zu einer absoluten URL zu machen
        match = re.match(r'^(http://[^/]+)', base_url)
        if match:
            base = match.group(1)
            return base + location
        else:
            raise Exception("Ungültige Basis-URL.")
    else:
        # Anfügen des relativen Pfades an den aktuellen Pfad der Basis-URL
        base_path = base_url.rstrip('/')
        return base_path + '/' + location


if __name__ == "__main__":
    # Prüfen, ob die richtigen Kommandozeilenargumente übergeben wurden
    if len(sys.argv) != 3:
        print("Verwendung: python3 HttpClient.py <URL> <Ausgabedatei>")
        sys.exit(1)

    url = sys.argv[1]
    output_file = sys.argv[2]

    max_redirects = 10
    redirect_count = 0

    while True:
        try:
            # URL parsen
            try:
                scheme, host, path, port = parseUrl(url)
            except ValueError as e:
                print(f"Fehler beim Parsen der URL '{url}': {e}")
                sys.exit(1)

            # Nur 'http' Schema unterstützen (HTTPS wird nicht unterstützt)
            if scheme != 'http':
                print("Nur das 'http'-Schema wird unterstützt.")
                sys.exit(1)

            # Aufbau des HTTP-Requests
            http_request = buildRequest(host, path)

            # Senden der Anfrage und Empfangen der Antwort
            response = sendRequest(host, port, http_request)

            # Parsen der Response
            status_code, headers, body, status_message = parseResponse(response)

            print(f"HTTP-Statuscode: {status_code}")

            if status_code == 200:
                # Speichern des Response-Bodys in der Ausgabedatei
                try:
                    with open(output_file, 'wb') as f:
                        f.write(body)
                    print(f"Antwort erfolgreich in '{output_file}' gespeichert.")
                except IOError as e:
                    print(f"Fehler beim Speichern der Datei: {e}")
                    sys.exit(1)
                break  # Erfolgreich, Schleife beenden
            elif status_code in [301, 302, 303, 307, 308]:
                # Umleitung behandeln, falls einer der genannten Redirect-Statuscodes erhalten wird
                redirect_url = headers.get('Location')
                if redirect_url:
                    print(f"Umleitung zu {redirect_url}")
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        print("Zu viele Umleitungen.")
                        sys.exit(1)
                    # Neue URL auflösen, indem die Redirect-URL mit der Basis-URL kombiniert wird
                    redirect_url = resolve_redirect_url(url, redirect_url)
                    url = redirect_url
                    continue
                else:
                    print("Umleitung erhalten, aber kein 'Location'-Header vorhanden.")
                    sys.exit(1)
            elif 400 <= status_code <= 499:
                # Fehler im Clientbereich (4xx)
                print(f"Client-Fehler aufgetreten: {status_code} - {status_message}")
                sys.exit(1)
            elif 500 <= status_code <= 599:
                # Fehler im Serverbereich (5xx)
                print(f"Server-Fehler aufgetreten: {status_code} - {status_message}")
                sys.exit(1)
            else:
                # Unbekannter Statuscode, nicht weiter behandelt
                print(f"Unbekannter Statuscode: {status_code} - {status_message}")
                sys.exit(1)
        except NotImplementedError as nie:
            print(f"Fehler: {nie}")
            sys.exit(1)
        except Exception as e:
            print(f"Fehler: {e}")
            sys.exit(1)
