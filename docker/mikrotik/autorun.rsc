# MikroTik RouterOS startup script
# Mount at /rw/disk/autorun.rsc — runs automatically on first boot.
# Configures FreeRADIUS as the authentication/accounting server.
#
# "freeradius" resolves via Docker DNS to the FreeRADIUS container on the
# netgrid network.  The secret must match clients.conf's netgrid_network block.

/radius
add address=freeradius \
    secret=netgrid_radius_secret \
    authentication-port=1812 \
    accounting-port=1813 \
    service=ppp \
    name=netgrid-freeradius

# Enable RADIUS for PPP (PPPoe/L2TP/PPTP) authentication.
# Uncomment the lines below when you want PPPoE subscribers to authenticate
# through FreeRADIUS (requires a PPP secret on the MikroTik + a matching
# subscriber in NetGrid).
#
# /ppp aaa
# set use-radius=yes accounting=yes interim-update=5m

# Enable RADIUS for hotspot authentication (captive portal).
# Uncomment when configuring a hotspot interface.
#
# /ip hotspot profile
# set [ find default=yes ] use-radius=yes
