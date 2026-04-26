#!/bin/bash
# 5x cold-boot stress test for OpenWrt on RT2600ac.
#
# Drives a Siglent SPD3303X bench supply (over LAN/SCPI on TCP 5025)
# to power-cycle the router, then verifies the system comes up healthy
# on each cycle: br-lan IP, both APs broadcasting, factory MAC, USB
# mount, WAN associated.
#
# Bench layout assumed by this script (override the env vars below):
#   - SCPI_HOST  : Siglent IP, reachable from $PI_HOST
#   - PI_HOST    : optional jump host on the bench network that can
#                  reach both the Siglent and the router
#   - ROUTER     : router LAN IP
#   - PI_KEY     : SSH key for $PI_USER@$PI_HOST
#   - EXPECT_MAC : factory base MAC of the unit (vendorpart 0xd0)
#
# If you don't have a jump host, run this directly from a machine
# that can reach both SCPI_HOST and ROUTER, and remove the -J args.

PI_KEY=${PI_KEY:-~/.ssh/id_ed25519}
PI_USER=${PI_USER:-pi}
PI_HOST=${PI_HOST:-192.168.1.10}
ROUTER=${ROUTER:-192.168.1.1}
SCPI_HOST=${SCPI_HOST:-192.168.50.2}
EXPECT_MAC=${EXPECT_MAC:-00:11:32:00:00:00}   # set this to your unit's vendorpart base MAC

SIG_CMD() {
  ssh -i $PI_KEY -o ConnectTimeout=5 $PI_USER@$PI_HOST "
    python3 -c \"
import socket
s = socket.create_connection(('$SCPI_HOST', 5025), timeout=5)
s.sendall(b'OUTP CH1,$1\n'); s.close()
\""
}

SSH_R="ssh -i $PI_KEY -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes -J $PI_USER@$PI_HOST root@$ROUTER"

PASS=0; FAIL=0
for i in 1 2 3 4 5; do
  echo
  echo "=========================================="
  echo "  COLD-BOOT CYCLE $i / 5"
  echo "=========================================="
  SIG_CMD OFF; sleep 4; SIG_CMD ON
  T0=$(date +%s)

  UP=0
  for w in $(seq 1 40); do
    sleep 3
    if $SSH_R 'echo up' 2>/dev/null | grep -q up; then
      UP=1
      T1=$(date +%s); BT=$((T1-T0))
      echo "  → up after ${BT}s"
      break
    fi
  done

  if [ $UP -eq 0 ]; then
    echo "  ✗ FAILED to come up"; FAIL=$((FAIL+1)); continue
  fi

  # Allow services to settle (ath10k firmware load takes ~50s)
  sleep 75

  H=$($SSH_R '
    echo UPT $(cut -d. -f1 /proc/uptime)
    echo BRLAN $(ip -4 -o addr show br-lan 2>/dev/null | grep -c "inet ")
    echo AP5 $(iw dev phy0-ap0 info 2>/dev/null | grep -c "type AP")
    echo AP2 $(iw dev phy1-ap0 info 2>/dev/null | grep -c "type AP")
    echo MAC $(cat /sys/class/net/br-lan/address)
    echo USB $(mount | grep -c "/mnt/data")
    echo WAN $(ifstatus wwan 2>/dev/null | grep -c "\"up\": true")
  ' 2>/dev/null)

  echo "$H" | sed "s/^/  /"
  brlan=$(echo "$H" | awk '/^BRLAN/{print $2}')
  ap5=$(echo "$H" | awk '/^AP5/{print $2}')
  ap2=$(echo "$H" | awk '/^AP2/{print $2}')
  mac=$(echo "$H" | awk '/^MAC/{print $2}')
  mnt=$(echo "$H" | awk '/^USB/{print $2}')
  wan=$(echo "$H" | awk '/^WAN/{print $2}')

  if [ "$brlan" = "1" ] && [ "$ap5" = "1" ] && [ "$ap2" = "1" ] && \
     [ "$mac" = "$EXPECT_MAC" ] && [ "$mnt" = "1" ] && [ "$wan" = "1" ]; then
    echo "  ✓ PASS"; PASS=$((PASS+1))
  else
    echo "  ✗ FAIL — incomplete bring-up"; FAIL=$((FAIL+1))
  fi
done

echo
echo "==================================================="
echo "  FINAL: $PASS passed, $FAIL failed of 5 cycles"
echo "==================================================="
