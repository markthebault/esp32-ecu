idf_component_register(SRCS "app.cpp" "web_config.cpp" "espnow.cpp" INCLUDE_DIRS "../include"
    REQUIRES esp_driver_gpio esp_driver_spi esp_driver_mcpwm esp_driver_gptimer esp_timer driver nvs_flash esp_wifi esp_event esp_netif esp_http_server json mbedtls esp_driver_rmt)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror)
