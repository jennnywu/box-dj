idf_component_register(SRCS "main.c" "motors.c" "sensors.c" "comm.c" "inputs.c"
                       INCLUDE_DIRS "." "../include"
                        REQUIRES driver esp_timer esp_adc)
