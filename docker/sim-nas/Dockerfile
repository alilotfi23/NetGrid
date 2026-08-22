# sim-nas: a lightweight simulated NAS for testing FreeRADIUS authentication.
# Sends RADIUS Access-Request packets to FreeRADIUS, acting as a virtual
# NAS device.  Works on any Docker host (no TUN/TAP required).
#
# For a real MikroTik RouterOS container, see docker/mikrotik/ and use a
# Linux host with /dev/net/tun support.

FROM alpine:3.19
RUN apk add --no-cache freeradius-utils python3
COPY nas_client.py /nas_client.py
CMD ["python3", "/nas_client.py"]
