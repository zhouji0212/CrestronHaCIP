# CrestronHaCIP

## Crestron Connect To Homeassistant Use Crestron-over-IP (CIP) Protocol.

this project is mix from npop-crestron-homeassistant component(https://github.com/npope/home-assistant-crestron-component)

and klenae's Python CIP Protocol(https://github.com/klenae/python-cipclient)
Support switch、single dimmer、colortemp and rgbw color
Update Support OpenClose Cover
### 2025.3.10 Update
support Homeassistant 2023.3.0
### Use Demo:

##### Edit the config.yaml like this:

    crestroncip:
    ip: 192.168.40.103
    port: 41794
    ipid: 0x0a
    switch:
        - platform: crestroncip
            name: "TestSwitch1"
            switch_join: 1
            count: 2
        - platform: crestroncip
            name: "TestSwitch2"
            switch_join: 2
            count: 4
        - platform: crestroncip
            name: "TestSwitch3"
            switch_join: 3
    light:
        - platform: crestroncip
            name: "Light1"
            brightness_join: 1
            type: brightness
        - platform: crestroncip
            name: "Light2"
            brightness_join: 2
            type: brightness
        - platform: crestroncip
            name: "Light10"
            brightness_join: 8
            color_temp_join: 9
            type: color_temp
        - platform: crestroncip
            name: "Light11"
            brightness_join: 7
            color_h_join: 5
            color_s_join: 6
            type: color_hs
