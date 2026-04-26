#!/usr/bin/env python3

import socket
import sys


HOST = "10.0.0.69"
PORT = 5025
TIMEOUT_SECONDS = 3.0
CH1_MASK = 0x10


class ScpiError(Exception):
    pass


def recv_line(sock: socket.socket) -> str:
    data = bytearray()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break

    if not data:
        raise ScpiError("no response from instrument")

    return data.decode("ascii", errors="replace").strip()


def send_command(sock: socket.socket, command: str) -> None:
    sock.sendall(f"{command}\n".encode("ascii"))


def query(sock: socket.socket, command: str) -> str:
    send_command(sock, command)
    return recv_line(sock)


def parse_status_mask(raw_status: str) -> int:
    text = raw_status.strip()
    try:
        return int(text, 0)
    except ValueError as exc:
        raise ScpiError(f"unexpected SYST:STAT? response: {text!r}") from exc


def ch1_is_on(status_mask: int) -> bool:
    return bool(status_mask & CH1_MASK)


def state_label(is_on: bool) -> str:
    return "ON" if is_on else "OFF"


def main() -> int:
    try:
        with socket.create_connection((HOST, PORT), timeout=TIMEOUT_SECONDS) as sock:
            sock.settimeout(TIMEOUT_SECONDS)

            idn = query(sock, "*IDN?")
            print(f"Connected to: {idn}")

            before_raw = query(sock, "SYST:STAT?")
            before_mask = parse_status_mask(before_raw)
            before_on = ch1_is_on(before_mask)
            target_on = not before_on
            target_state = state_label(target_on)

            print(f"CH1 before: {state_label(before_on)} (status={before_raw})")
            send_command(sock, f"OUTP CH1,{target_state}")

            after_raw = query(sock, "SYST:STAT?")
            after_mask = parse_status_mask(after_raw)
            after_on = ch1_is_on(after_mask)

            print(f"CH1 after:  {state_label(after_on)} (status={after_raw})")

            if after_on != target_on:
                print(
                    f"Toggle failed: expected CH1 {target_state}, "
                    f"but instrument reports {state_label(after_on)}.",
                    file=sys.stderr,
                )
                return 2

            print(f"Toggle succeeded: CH1 changed from {state_label(before_on)} to {state_label(after_on)}.")
            return 0

    except (OSError, socket.timeout, ScpiError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
