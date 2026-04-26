define Device/synology_rt2600ac
	DEVICE_VENDOR := Synology
	DEVICE_MODEL := RT2600ac
	SOC := qcom-ipq8065
	DEVICE_DTS := qcom-ipq8065-rt2600ac
	BLOCKSIZE := 128k
	PAGESIZE := 2048
	KERNEL_SIZE := 4096k
	KERNEL := kernel-bin | append-dtb | uImage none
	KERNEL_NAME := zImage
	IMAGE_SIZE := 32m
	IMAGES := sysupgrade.bin
	IMAGE/sysupgrade.bin := append-kernel | pad-to $$$$(KERNEL_SIZE) | append-rootfs | \
		pad-rootfs | append-metadata
	DEVICE_PACKAGES := kmod-ath10k-ct ath10k-firmware-qca9984-ct \
		kmod-usb-storage kmod-usb3 kmod-usb-ledtrig-usbport
endef

