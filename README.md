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

```yaml
action: pgnig_gas_sensor.add_reading
data:
  meter_id: "12345678"          # the ID shown in the device name
  value: 1234                   # meter state in m³
  # date: "2026-08-08"          # optional, defaults to today
  # consent_meter_reset: true   # only when the meter was replaced / rolled over
  # config_entry_id: ...        # only with more than one Orlen account
```

The service returns the accepted reading, so it can be used with
`response_variable`:

```yaml
action: pgnig_gas_sensor.add_reading
data:
  meter_id: "12345678"
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