FROM alpine:3.20

RUN apk add --no-cache freeradius freeradius-postgresql freeradius-utils \
    && rm /etc/raddb/mods-enabled/sql /etc/raddb/sites-enabled/default

# mods-enabled/sql and sites-enabled/default are package symlinks into
# mods-available/sites-available; COPY would write through them and clobber
# the stock files, so the rm above breaks the symlinks first.
COPY raddb/clients.conf /etc/raddb/clients.conf
COPY raddb/mods-enabled/sql /etc/raddb/mods-enabled/sql
COPY raddb/policy.d/lockout /etc/raddb/policy.d/lockout
COPY raddb/sites-enabled/default /etc/raddb/sites-enabled/default
COPY raddb/sites-enabled/coa /etc/raddb/sites-enabled/coa

EXPOSE 1812/udp 1813/udp

CMD ["radiusd", "-f", "-X"]
