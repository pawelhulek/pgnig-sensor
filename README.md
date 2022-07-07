# PGNIG Sensor 

This sensor is gathering gas usage data for PGNIG clients.

It uses API from https://ebok.pgnig.pl/

## Manual Configuration
Sample configuration

```yaml
sensor:
  - platform: pgnig_gas_sensor
    username: YOUR USERNAME
    password: YOUR PASSWORD
```

## Technical Details

The sensor uses API from https://ebok.pgnig.pl 
and is particularly focused on the last reading endpoint.

Currently, it reads only last reading value and wear value. 
The measurement unit is volume cubic meters.

The data is refreshed every 8 hours or on the sensor startup.

### Sample entity attributes:

```
state_class: total_increasing
wear: 222
wear_unit_of_measurment: m³
unit_of_measurement: m³
device_class: gas
friendly_name: PGNIG Gas Sensor 1111111111111111111111
```

### Running tests

```bash
$ pip3 install -r requirements_test.txt
```

The dependencies are installed - you can invoke `pytest` to run the tests.

```bash
$ pytest
```

Anything else? Post a [question.](https://github.com/pawelhulek/pgnig-sensor/issues/new)