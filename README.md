# PGNIG Sensor 

This sensor is gathering gas usage data for PGNIG clients.

It uses API from https://ebok.myorlen.pl/

## Manual Configuration
Sample configuration

```yaml
sensor:
  - platform: pgnig_gas_sensor
    username: YOUR USERNAME
    password: YOUR PASSWORD
```
It is recommended to confiure the sensor through the UI.

## Through the interface
1) Navigate to Settings > Devices & Services and then click Add Integration
2) Search for PGNIG gas sensor
3) Enter your credentials (e-mail and password)

## Technical Details

The sensor uses API from https://ebok.pgnig.pl 
and is particularly focused on the last reading endpoint. 

The data is refreshed every 8 hours or on the sensor startup.
The sensors are not updated if the data hasn't changed.
There are 3 different sensors created.

### Gas sensor

Currently, it reads last reading value and wear value. 
The measurement unit is volume cubic meters.

### Invoice sensor

Sensor reading last unpaid invoice.

The value of the sensor is amount to be paid in PLN. 
As a attributes the sensor is also providing due date, amount to pay, used wear and used wear in KWH.

### Cost tracking sensor

The sensor is tracking cost from the latest invoice. 
It divides amount to be paid by wear in KWH. Can be used in energy dashboard to track the cost.

## Services

### `pgnig_gas_sensor.refresh`

Forces an immediate update of every sensor belonging to the integration.

### `pgnig_gas_sensor.add_reading`

Sends a meter reading to Orlen EBOK — the automation equivalent of filling in
the "podaj odczyt" form on the website. Orlen only accepts readings inside the
reporting window for the meter; outside it, the call fails with the same error
the website shows.

> **Check the value before you send it.** Orlen bills from the number you
> submit, so a mistyped or badly scaled reading — a digit too many, or a sensor
> reporting something other than the meter's own total — turns into an invoice
> for gas you never used. An accepted reading can sometimes still be withdrawn
> on the Orlen website; `can_be_cancelled` in the response says whether that one
> can. Automations that submit a templated value are worth testing with the
> template rendered in Developer tools first.

Two guards run before anything is sent, both measured against the reading the
sensor is currently showing:

| Situation | What happens |
|---|---|
| Value **lower** than the last reading | Refused — a meter total only climbs. Pass `consent_meter_reset: true` if the meter really was replaced or rolled over. |
| Value **more than 500 m³ above** the last reading | Refused — that is the scale of a mistyped reading. Pass `confirm_large_increase: true` if the value is right. |

Neither can run when Home Assistant has no previous reading for the meter yet,
so the first submission after setup is unchecked. The 500 m³ limit is
`MAX_READING_INCREASE_M3` in `const.py`.

In the UI, pick the meter from the device list — there is no need to type its
number. In YAML, `device_id` is what the picker fills in:

```yaml
action: pgnig_gas_sensor.add_reading
data:
  device_id: 1a2b3c...          # the meter, as picked in the UI
  value: 1234                   # meter state in m³
  # date: "2026-08-08"          # optional, defaults to today
  # consent_meter_reset: true   # only when the meter was replaced / rolled over
```

The picked meter also identifies the account, so `config_entry_id` is only
needed when passing `meter_id` by hand with more than one Orlen account:

```yaml
action: pgnig_gas_sensor.add_reading
data:
  meter_id: "12345678"          # meter number, if it has no device in HA
  value: 1234
  # config_entry_id: ...
```

The service returns the accepted reading, so it can be used with
`response_variable`:

```yaml
action: pgnig_gas_sensor.add_reading
data:
  device_id: 1a2b3c...
  value: "{{ states('sensor.gas_meter') | round(0) }}"
response_variable: submitted
```

`submitted` then holds `meter_id`, `value`, `added_at_utc` and
`can_be_cancelled`.

### Running tests

```bash
$ pip3 install -r requirements_test.txt
```

The dependencies are installed - you can invoke `pytest` to run the tests.

```bash
$ pytest
```

# Legal notice
This is a personal project and isn't in any way affiliated with, sponsored or endorsed by POLSKIE GÓRNICTWO NAFTOWE I GAZOWNICTWO S A (PGNIG).

All product names, trademarks and registered trademarks in (the images in) this repository, are property of their respective owners. All images in this repository are used by the project for identification purposes only.

The data source for this integration is https://ebok.myorlen.pl/

The author of this project categorically rejects any and all responsibility for the data that were presented by the integration.

Anything else? Post a [question.](https://github.com/pawelhulek/pgnig-sensor/issues/new)