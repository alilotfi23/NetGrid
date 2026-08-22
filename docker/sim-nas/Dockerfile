# sim-nas: a lightweight simulated NAS for testing FreeRADIUS
# authentication *and* the RFC 5176 CoA/disconnect path. It sends periodic
# RADIUS Access-Requests to FreeRADIUS and answers Disconnect/CoA-Requests
# on UDP 3799 with a real Disconnect-ACK, so FastAPI's pyrad disconnect
# service gets an ACK (and the audit trail records result: ack). Works on
# any Docker host (no TUN/TAP required).
#
# For a real MikroTik RouterOS container, see docker/mikrotik/ and use a
# Linux host with /dev/net/tun support.

FROM alpine:3.19
RUN apk add --no-cache freeradius-utils python3
COPY nas_client.py /nas_client.py
COPY coa_server.py /coa_server.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 3799/udp
CMD ["/entrypoint.sh"]
