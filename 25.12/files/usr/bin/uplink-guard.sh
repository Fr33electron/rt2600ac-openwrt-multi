#!/bin/sh
# uplink-guard — bring a WAN uplink back if unit-2 (router mode) loses its default route.
# Ported+generalized from unit-1. Walks unit-2's full STA roster in priority order.
# Mode-aware: no-op unless current mode is 'router'. Runs from cron every 3 min.
STATE=/etc/unit2-modes/.current
[ "$(cat $STATE 2>/dev/null)" = "router" ] || exit 0          # only guard in router mode
ip route | grep -q '^default' && exit 0                        # already have a route
logger -t uplink-guard "no default route - walking uplink roster"

# priority: sta_name  network   (first that yields a default route wins)
ROSTER="sta_u1:wwan5 sta_att5:wwan5 sta_att24:wwanv sta_att:wwanx sta_xfin:wwanx sta_wwan:wwanv"

for entry in $ROSTER; do
    sta=${entry%%:*}; net=${entry##*:}
    uci -q get wireless.$sta >/dev/null || continue
    logger -t uplink-guard "trying $sta -> $net"
    # enable only this STA, disable the rest of the roster
    for e2 in $ROSTER; do s2=${e2%%:*}; uci -q set wireless.$s2.disabled=1; done
    uci -q set wireless.$sta.disabled=0
    uci -q commit wireless
    wifi up >/dev/null 2>&1
    sleep 8
    ifup "$net" >/dev/null 2>&1
    sleep 10
    if ip route | grep -q '^default'; then
        logger -t uplink-guard "recovered via $sta ($net)"
        exit 0
    fi
done
logger -t uplink-guard "roster exhausted - still no default route"
exit 0
