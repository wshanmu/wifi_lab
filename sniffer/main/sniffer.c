#include "esp_wifi.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include <string.h>
#include <stdio.h>
#include "xt_instr_macros.h" // For RSR(CCOUNT, ...) cycle-counter read
#include "xtensa/config/xt_specreg.h" // For the CCOUNT register constant

#define LEN_MAC_ADDR 20

// Spoofed transmitter (Address 2) that injector.c's Packet[] uses - must be
// kept in sync with that file if the fake address there ever changes.
#define INJECTOR_SPOOFED_MAC "AA:BB:BB:BB:BB:BB"

// First frame-control byte of injector.c's Packet[]: Data type, Null-function
// subtype. Used to reject other Data frames that happen to share the MAC.
#define INJECTED_FRAME_CTRL_BYTE 0x48

/* Holds the decimal-formatted CSI samples for the packet currently being
 * logged. Static (not stack-allocated) since it's rebuilt fully on every
 * callback and is too large to put safely on a task stack. */
static char csi[2000];

/*
 * CSI callback: fires for every CSI report the driver produces.
 * Logs timestamp/rssi/raw CSI samples, filtered down to just the injector's
 * spoofed frames (see INJECTOR_SPOOFED_MAC / INJECTED_FRAME_CTRL_BYTE above).
 */
void receive_csi_cb(void *ctx, wifi_csi_info_t *data)
{
	uint32_t cycle_counts;
	RSR(XT_REG_CCOUNT, cycle_counts);

	char senderMac[LEN_MAC_ADDR] = {0};
	sprintf(senderMac, "%02X:%02X:%02X:%02X:%02X:%02X",
			data->mac[0], data->mac[1], data->mac[2],
			data->mac[3], data->mac[4], data->mac[5]);

	// Only log the injector's spoofed frames: match its fake sender address
	// and the exact frame-control byte, in case another Data frame ever
	// reuses that MAC.
	if (strcmp(senderMac, INJECTOR_SPOOFED_MAC)) return;
	if (data->hdr[0] != INJECTED_FRAME_CTRL_BYTE) return;

	int offset = 0;
	for (int i = 0; i < data->len; i++) {
		offset += snprintf(csi + offset, sizeof(csi) - offset, "%d ", data->buf[i]);
		if (offset >= (int)sizeof(csi))
			break;
	}

	printf("<timestamp>%lu</timestamp><rssi>%d</rssi><address>%s</address>%s\n",
		(unsigned long)cycle_counts, data->rx_ctrl.rssi, senderMac, csi);
}

void app_main()
{
	// Initialize NVS
	esp_err_t ret = nvs_flash_init();
	if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_ERROR_CHECK(nvs_flash_erase());
		ret = nvs_flash_init();
	}
	ESP_ERROR_CHECK(ret);

	wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
	cfg.csi_enable = 1;
	ESP_ERROR_CHECK(esp_wifi_init(&cfg));
	ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
	ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
	ESP_ERROR_CHECK(esp_wifi_start());

	// The injector sends Data-type (Null-function) frames, not Control
	// frames, so only Data needs to reach the CSI/promiscuous pipeline.
	wifi_promiscuous_filter_t filter_promi = {
		.filter_mask = WIFI_PROMIS_FILTER_MASK_DATA,
	};
	ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter_promi));
	ESP_ERROR_CHECK(esp_wifi_set_channel(1, 0)); // <-- Change the channel
	ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
	ESP_ERROR_CHECK(esp_wifi_set_csi(1));
	vTaskDelay(1000 / portTICK_PERIOD_MS); // Let the driver settle before registering the callback

	ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(&receive_csi_cb, NULL));

	printf("ESP32 initialized!\n");
}
