import requests

town_input = "tenczynek"
street_input = "Chrzanowska"
house_number_input = "39"

headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json',
}

towns_url = "https://ecoharmonogram.pl/api/api.php?action=getTowns"
scheduled_periods_url = "https://ecoharmonogram.pl/api/api.php?action=getSchedulePeriods"
streets_url = "https://ecoharmonogram.pl/api/api.php?action=getStreets"
schedules_url = "https://ecoharmonogram.pl/api/api.php?action=getSchedules"
response = requests.get(towns_url, headers=headers)
response.encoding = "utf-8-sig"

data = response.json()
filteredItem = filter(lambda x: town_input.lower() == x.get('name').lower(), data.get('towns'))
town = list(filteredItem)[0]

print(town)

response = requests.get(scheduled_periods_url + "&townId=" + town.get("id"), headers=headers)
response.encoding = "utf-8-sig"

data = response.json()
schedule_periods = data.get("schedulePeriods")

print(schedule_periods)

for sp in schedule_periods:
    response = requests.get(
        streets_url + "&streetName=" + street_input + "&number=" + house_number_input + "&townId=" + town.get("id") +
        "&schedulePeriodId=" + sp.get("id"), headers=headers)
    response.encoding = "utf-8-sig"
    streets = response.json().get("streets")
    print(streets)
    for s in streets:
        response = requests.get(schedules_url + "&streetId=" + s.get("id") + "&schedulePeriodId=" + sp.get("id"),
                                headers=headers)
        response.encoding = "utf-8-sig"
        print(response.json())
