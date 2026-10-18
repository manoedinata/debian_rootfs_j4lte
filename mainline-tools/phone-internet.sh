#!/bin/bash
#
# Shares this PC's internet connection with the phone over the USB RNDIS link
# (PC 172.16.42.2, phone 172.16.42.1). Everything is runtime-only, on both ends:
# nothing is written to the phone's root filesystem, and the PC's rules are gone
# at the next reboot of the PC (or with `down`).
#
#   phone-internet.sh up      NAT on the PC, default route and DNS on the phone
#   phone-internet.sh down    undo it
#   phone-internet.sh status  check from the phone
#
# env: HOST (phone ssh target, default root@172.16.42.1), DNS (default 1.1.1.1)
#
set -euo pipefail

HOST="${HOST:-root@172.16.42.1}"
DNS="${DNS:-1.1.1.1}"
PHONE_IP="${HOST#*@}"
NET=172.16.42.0/24
PC_IP=172.16.42.2
SSH=(ssh -o ConnectTimeout=8 -o BatchMode=yes "$HOST")
ssh_q() { "${SSH[@]}" "$@" 2> >(grep -v 'post-quantum\|store now\|openssh.com/pq' >&2); }

usb_if=$(ip -o route get "$PHONE_IP" | sed -n 's/.* dev \([^ ]*\).*/\1/p')
wan_if=$(ip -o route get 1.1.1.1 | sed -n 's/.* dev \([^ ]*\).*/\1/p')

rule() { # rule <table-args...> -- add if missing
	if sudo iptables "${@/-A/-C}" 2>/dev/null; then return; fi
	sudo iptables "$@"
}

case "${1:-}" in
up)
	echo "==> PC: $usb_if <-> $wan_if"
	sudo sysctl -qw net.ipv4.ip_forward=1
	# in front of the Docker/Tailscale/libvirt chains
	sudo iptables -C FORWARD -i "$usb_if" -o "$wan_if" -j ACCEPT 2>/dev/null ||
		sudo iptables -I FORWARD 1 -i "$usb_if" -o "$wan_if" -j ACCEPT
	sudo iptables -C FORWARD -i "$wan_if" -o "$usb_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null ||
		sudo iptables -I FORWARD 2 -i "$wan_if" -o "$usb_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
	sudo iptables -t nat -C POSTROUTING -s "$NET" -o "$wan_if" -j MASQUERADE 2>/dev/null ||
		sudo iptables -t nat -A POSTROUTING -s "$NET" -o "$wan_if" -j MASQUERADE
	echo "==> phone: default route via $PC_IP, DNS $DNS"
	ssh_q "ip route replace default via $PC_IP dev rndis0 &&
		echo 'nameserver $DNS' > /run/resolv.phone-internet &&
		{ mountpoint -q /etc/resolv.conf || mount --bind /run/resolv.phone-internet /etc/resolv.conf; } &&
		cat /etc/resolv.conf"
	;;
down)
	sudo iptables -D FORWARD -i "$usb_if" -o "$wan_if" -j ACCEPT 2>/dev/null || true
	sudo iptables -D FORWARD -i "$wan_if" -o "$usb_if" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
	sudo iptables -t nat -D POSTROUTING -s "$NET" -o "$wan_if" -j MASQUERADE 2>/dev/null || true
	ssh_q "ip route del default via $PC_IP dev rndis0 2>/dev/null; umount /etc/resolv.conf 2>/dev/null; rm -f /run/resolv.phone-internet; true"
	echo "==> undone (net.ipv4.ip_forward left as it was)"
	;;
status)
	ssh_q "ip route; cat /etc/resolv.conf; ping -c2 -W3 1.1.1.1 && getent hosts deb.debian.org"
	;;
*)
	sed -n '2,15p' "$0"
	exit 1
	;;
esac
