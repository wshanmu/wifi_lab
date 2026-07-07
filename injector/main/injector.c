#include "esp_wifi.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include <string.h>
#include <stdio.h>

/* Frame definition dc:ef:ca:45:c2:e3 f2:6e:0b:d2:1a:13 */
uint8_t Packet[24] = {
/*  0 - 3  */ 0x48, 0x01, 0x00, 0x00, // Type/Subtype: Null function frame
/*  4 - 9  */ 0xa4, 0xf0, 0x0f, 0xdf, 0xb4, 0x0d, // <-- change with the MAC address of target
/* 10 - 15 */ 0xAA, 0xBB, 0xBB, 0xBB, 0xBB, 0xBB, // Our transmitter fake address
/* 16 - 21 */ 0xa4, 0xf0, 0x0f, 0xdf, 0xb4, 0x0d, // Destination
// Fixed parameters
/* 22 - 23 */ 0x00, 0x00, // Fragment & sequence number (will be done by the SDK)
};

/* Continuously transmits the fake 802.11 frame in `Packet`.
 * Never returns - this is the injector's whole job. */
void send_frame(void)
{
	uint32_t packetSize = sizeof(Packet);

	while (true) {
		// Sending faster than this delay tends to destabilize the radio.
		ESP_ERROR_CHECK(esp_wifi_80211_tx(WIFI_IF_STA, Packet, packetSize, false));
		vTaskDelay(40 / portTICK_PERIOD_MS);
	}
}

void app_main()
{
	esp_err_t ret = nvs_flash_init();
	if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
		ESP_ERROR_CHECK(nvs_flash_erase());
		ret = nvs_flash_init();
	}
	ESP_ERROR_CHECK(ret);

	wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
	ESP_ERROR_CHECK(esp_wifi_init(&cfg));
	ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
	ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));

	// Fixes the rate used for raw-injected 802.11 frames. Must be called
	// after esp_wifi_init() and before esp_wifi_start(). WIFI_PHY_RATE_6M
	// picked for range/reliability; see wifi_phy_rate_t for other options
	// (802.11b/g/n rates only - 11a/ac/ax aren't supported here).
	ESP_ERROR_CHECK(esp_wifi_config_80211_tx_rate(WIFI_IF_STA, WIFI_PHY_RATE_6M));

	ESP_ERROR_CHECK(esp_wifi_start());
	ESP_ERROR_CHECK(esp_wifi_set_channel(1, 0));

	printf("ESP32 initialized! Starting injection...\n");
	send_frame();
}
