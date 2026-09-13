from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


healthy = True


class DemoHandler(BaseHTTPRequestHandler):

    def send_text_response(self, status_code, message):
        self.send_response(status_code)

        self.send_header(
            "Content-Type",
            "text/plain"
        )

        self.end_headers()

        self.wfile.write(
            message.encode("utf-8")
        )


    def do_GET(self):
        global healthy

        if self.path == "/health":

            if healthy:
                self.send_text_response(
                    200,
                    "Application is healthy"
                )

            else:
                self.send_text_response(
                    500,
                    "Application is unhealthy"
                )

        elif self.path == "/fail":

            healthy = False

            self.send_text_response(
                200,
                "Application switched to unhealthy"
            )

        elif self.path == "/recover":

            healthy = True

            self.send_text_response(
                200,
                "Application switched to healthy"
            )

        else:

            self.send_text_response(
                404,
                "Not found"
            )


    def log_message(self, format, *args):
        return


def main():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 8000),
        DemoHandler
    )

    print(
        "Demo application running at "
        "http://127.0.0.1:8000"
    )

    print(
        "Health endpoint: "
        "http://127.0.0.1:8000/health"
    )

    print(
        "Fail endpoint: "
        "http://127.0.0.1:8000/fail"
    )

    print(
        "Recovery endpoint: "
        "http://127.0.0.1:8000/recover"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("\nDemo application stopped.")

    finally:
        server.server_close()


if __name__ == "__main__":
    main()