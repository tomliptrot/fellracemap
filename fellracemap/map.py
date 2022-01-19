import os
from calendar import month_name
from collections import OrderedDict
from operator import itemgetter
from pathlib import Path
from tkinter import N

import folium
import pandas as pd
import requests
from bs4 import BeautifulSoup, SoupStrainer
from loguru import logger

race_data_path = Path("data/race_data.csv")


def get_race_urls(index_url, base_url="https://races.fellrunner.org.uk"):
    logger.debug("Getting race urls")
    r = requests.get(index_url)
    soup = BeautifulSoup(r.content, features="lxml")
    race_urls = []
    for tr in soup.find_all("tr")[2:]:
        tds = tr.find_all("td")
        race_url = base_url + tds[1].a["href"]
        race_urls.append(race_url)
    return race_urls


def scrape_race(race_url):
    r = requests.get(race_url)
    soup = BeautifulSoup(r.content, features="lxml")
    lines = soup.find_all("li")
    race_data = [list(line.stripped_strings) for line in lines]
    race_dict = dict()
    for line in race_data:
        if line[0].endswith(":"):
            field_name = line[0][:-1]
            field_name = field_name.lower()
            field_name = field_name.replace(" ", "_")
            race_dict[field_name] = line[1]
    race_dict["race_url"] = race_url
    race_dict["title"] = soup.h1.string
    return race_dict


def get_postcodes(race_data):
    logger.debug("Geting postcode locations")
    postcode_regex = r"([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Ha-hJ-Yj-y][0-9]{1,2})|(([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Ha-hJ-Yj-y][0-9][A-Za-z]?))))\s?[0-9][A-Za-z]{2})"
    race_data["postcode"] = race_data.venue.str.extract(postcode_regex)[1]
    postcodes = race_data.postcode[~race_data.postcode.isnull()].to_list()
    batchsize = 99
    postcode_locations = []
    for i in range(0, len(postcodes), batchsize):
        pc_batch = postcodes[i : i + batchsize]
        postcode_locations += requests.post(
            url="https://postcodes.io/postcodes", json={"postcodes": pc_batch}
        ).json()["result"]
    fields = ["postcode", "latitude", "longitude"]
    pcd = [
        itemgetter(*fields)(location["result"])
        for location in postcode_locations
        if location["result"] is not None
    ]
    pcd = pd.DataFrame(pcd, columns=fields)
    return pcd


def build_race_data() -> pd.DataFrame:
    logger.debug("building race dataset")

    race_urls = get_race_urls("https://races.fellrunner.org.uk/races")
    for i in range(2, 8):
        race_urls += get_race_urls(
            f"https://races.fellrunner.org.uk/races/upcoming?page={i}"
        )
    # TODO load race data if needed and only scrape missing races.
    race_data = [scrape_race(race_url) for race_url in race_urls]
    race_data = pd.DataFrame(race_data)

    postcode_locations = get_postcodes(race_data)
    race_data = pd.merge(race_data, postcode_locations)
    # if no website raplace with race_url
    race_data.website.fillna(race_data.race_url, inplace=True)
    # TODO if no postcode, try looking up address -> https://developers.google.com/maps/documentation/geocoding/overview
    # TODO save race data
    return race_data


def make_map(race_data: pd.DataFrame):
    logger.debug("Making map")
    race_map = folium.Map(prefer_canvas=True, tiles="Stamen Terrain")

    months = OrderedDict()
    for month in month_name:
        months[month] = folium.FeatureGroup(name=month)

    def add_marker(point):
        marker = folium.Marker(
            location=[point.latitude, point.longitude],
            radius=2,
            weight=0,  # remove outline
            popup=f"{point.title} <br> {point.distance} <br> <a href='{point.website}' target='_blank'>{point.website}</a>",
            fill_color="#000000",
        )
        if point.month in month_name:
            marker.add_to(months[point.month])

    # use df.apply(,axis=1) to iterate through every row in your dataframe
    race_data[~race_data.longitude.isnull()].apply(add_marker, axis=1)

    for month, layer in months.items():
        layer.add_to(race_map)

    folium.LayerControl(collapsed=False, hideSingleBase=True).add_to(race_map)
    # Set the zoom to the maximum possible
    race_map.fit_bounds(race_map.get_bounds())
    # TODO add google analytics?
    # Save the map to an HTML file
    race_map.save(os.path.join("www/index.html"))

    return race_map


def main():
    race_data = build_race_data()
    race_data.to_csv(race_data_path)
    make_map(race_data)


# if main then run
if __name__ == "__main__":
    main()
