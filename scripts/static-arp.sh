#!/bin/bash
# Static ARP entries for lamps (workaround for poor ARP response from Tuya devices)

# Add your lamp ARP entries below:
# arp -s <IP> <MAC>  # lamp-name
arp -s YOUR_LAMP1_IP YOUR_LAMP1_MAC  # lamp1
arp -s YOUR_LAMP2_IP YOUR_LAMP2_MAC  # lamp2
arp -s YOUR_LAMP3_IP YOUR_LAMP3_MAC  # lamp3
