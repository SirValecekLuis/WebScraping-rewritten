from bs4 import BeautifulSoup
import requests
import re
import logging
from plyer import notification

"""This script serves for looking player's stats and based on that decide if they are suspicious or not."""

URL_LAMBDA = lambda x: "https://ugc-gaming.net/stats/cs/hlstats.php?mode=playerinfo&type=ajax&game=d2only&tab=weapons" \
                       f"&player={x}&killLimit=5&weap_sort=smhits&weap_sortorder=desc#tabweapons"

MAIN_URL = "https://ugc-gaming.net/stats/cs/hlstats.php?game=d2only"  # Url of main hlstats

LOG_FORMAT = "%(levelname)s %(asctime)s - %(message)s"

logging.basicConfig(filename="log.txt",
                    level=logging.INFO,
                    format=LOG_FORMAT,
                    filemode="a")

LOGGER = logging.getLogger()


def get_urls() -> (list, list):
    """
    This function is supposed to give us a list URLs of all players now playing.
    :return: Returns a list of all URLs
    """

    with open("log.txt", "a") as f:
        f.write("\n\n\n")
    LOGGER.info("Calling get_urls")

    try:
        text = requests.get(MAIN_URL).text  # Gets main text
    except requests.exceptions.ConnectionError:
        print("Error, page wasn't loaded")
        LOGGER.warning("Main page couldn't be loaded!")
        return [], []

    soup_page = BeautifulSoup(text, "lxml")  # breaks down by lxml
    table = soup_page.find_all("table", class_="livestats-table")[2]  # Find needed table with players
    list_urls = ["https://ugc-gaming.net" + text.get("href") for text in table.find_all("a")]  # All URLs of players
    list_weapon_urls = []  # All URLs of player's weapon stats
    for user_id in table.find_all("a"):  # Now search of all "a" tags
        text = re.search("[0-9]{1,10}", user_id.get("href")).group()  # Each "a" tag has a href of a player
        list_weapon_urls.append(URL_LAMBDA(text))  # and I will add an ID of player from url to a lambda function

    return list_urls, list_weapon_urls


def get_user_weap_html(url: str) -> list or None:
    """
    Based on url it will find a table content with weapon information in HTML code
    :param url: Raw webpage with weapon stats
    :return: list of HTML table contents or None if we got an error and dont want to continue
    """

    try:
        text = requests.get(url).text  # Gets url of
        data_table = BeautifulSoup(text, "lxml").find_all("table", class_="data-table")[1].find_all("tr")[1:]

        return data_table[:3]
    except IndexError:  # In case the player doesn't have enough data, the page is not generated yet with information
        LOGGER.warning(f"IndexError in weap_html, url: {url}")
        return None
    except requests.exceptions.ConnectionError:
        LOGGER.warning("User's page couldn't be loaded!")
        print("Page couldn't be loaded.")
        return None


def get_user_weap_stats(data: list) -> list or None:
    """
    Takes a data table in HTML format and parses it into player's data
    :param data: list with HTML text
    :return: 2D list of player's information or None if data is empty and we got no information from previous function
    """

    if not data:
        return None

    player_data = []
    for table in data:  # Data contains 3 different tables
        info = re.findall(r">.*<", str(table))[2:]  # Filter first two parts, I need only 4 values
        player_data_temp = [int(info[0].strip("<>").replace(",", ""))]  # The first value not processed to float
        for i in info[1:]:
            player_data_temp.append(float(i.strip("<>%")))  # "<43.5%>" - this is how a  number look like before strip
        player_data.append(player_data_temp)

    for i in range(3 - len(player_data)):  # If there are missing lists, I will make a new one to have always 3
        player_data.append([0, 0, 0, 0])

    return player_data  # Returns 2D list of user information


def get_user_main_stats(url: str) -> dict or None:
    """
    Based on main url, it will search for information such as ID, kills, name etc. at main page.
    :param url: Url of player's main page
    :return: dictionary of information about a player or None if an issue occurred
    """

    try:
        text = requests.get(url).text  # Text of a page
    except requests.exceptions.ConnectionError:
        LOGGER.warning("Player's main page couldn't be found!")
        print("Page couldn't be loaded.")
        return None

    soup_text = BeautifulSoup(text, "lxml")  # Using LXML to break it down
    table_content = soup_text.find_all("table", class_="data-table")[1].find_all("tr")[2:11]  # A list of 3 tables
    user_name = str(soup_text.find_all("title")[0]).split(" - ")[4].strip("\t</title>")  # Name got from title of page

    # Points are index 0
    # find_all gives back 2 things, and I need second one, then contents contain 1 thing(list) amd I need to strip it
    # after stripping, the text contains 2 parts eg. 17.9% (18%) but I don't need the 2nd number, so I split it by
    # space and take only the first number. After that I replace "," or "%" to get a string which is converted to int
    points = int(str(table_content[0].find_all("td")[1].contents[1]).strip("<b></b>").replace(",", ""))
    try:
        user_kd = float(table_content[3].find_all("td")[1].contents[0].strip("\r\n\t").split(" ")[0])
    except ValueError:  # If player has 0 deaths, user_kd is "-" and not a number which raises an error
        user_kd = 0
    user_accuracy = float(table_content[6].find_all("td")[1].contents[0].strip("\r\n\t").split(" ")[0].replace("%", ""))
    user_headshots = int(table_content[7].find_all("td")[1].contents[0].strip("\r\n\t").split(" ")[0].replace(",", ""))
    user_kills = int(table_content[8].find_all("td")[1].contents[0].strip("\r\n\t").split(" ")[0].replace(",", ""))

    try:
        user_hs_ratio = round(user_headshots / user_kills * 100, 1)
    except ZeroDivisionError:  # If user has 0 kills, zero division may occur
        user_hs_ratio = 0

    player_dict = {"name": user_name, "accuracy": user_accuracy, "headshots": user_headshots, "kills": user_kills,
                   "hs": user_hs_ratio, "kd": user_kd, "points": points
                   }
    LOGGER.info(f"Player {url} has been successfuly processed.")
    return player_dict


def evaluate_user_data(weap_data: list, user_data: dict) -> None:
    """
    Checks user information by many if statements and evaluates if a person is cheating or not.
    Player is considered to be suspicious if any rate is above these measures:
    65% HS  - Best players have around 60-63% max
    4.3 KD - Best players have around 4.1-4.2 max
    60% middle - Shouldn't be more than 60%, it is often being around 40-55%
    kills >= 8 - I will only care about a player who has more than 7 kills
    acc >= 27% - Accuracy shouldn't be more than 27%. Best players have around 26% even there are a few exceptions
    shots >= 20 - If player doesn't have with his most played weapon at least 10 shots, it is useless to decide.

    :param weap_data: 2D list of player's information
    :param user_data: dictionary of player's information (servers for showing information if a person is suspicious)
    :return: None, function will call another function for printing information about player if he is suspicious
    """

    suspicious = False

    if user_data["kills"] < 8:
        return

    for i, (shots, left, middle, right) in enumerate(weap_data):
        if i == 0 and shots < 20:
            return
        elif shots < 20:
            break
        elif middle > 62:
            suspicious = True

    if user_data["accuracy"] >= 27 and user_data["hs"] >= 65 or user_data["kd"] >= 4.3:
        # If any condition is met, this player can be cheating as these values are too high. Only a few good
        # players have the same numbers as I'm testing here
        suspicious = True

    if suspicious:
        player_found(user_data, weap_data)
        notification.notify(
            title="Cheater detector",
            message="A suspicious player has been found, check the log!",
            timeout=10
        )


def player_found(user_data: dict, weap_data: list) -> None:
    """
    When a suspicious person is found, this function serves as an announcement.
    :param user_data: dictionary with user data to print it
    :param weap_data: same for weapon data
    :return: None, just prints out a text
    """

    text = f"""
    Suspicious player found!\n
    User information:\n
    _________________________________________________________________________________________________________________\n
    Name: {user_data["name"]}\n
    _________________________________________________________________________________________________________________\n
    Points: {user_data["points"]}\n
    _________________________________________________________________________________________________________________\n
    KD ratio: {user_data["kd"]}\n
    _________________________________________________________________________________________________________________\n
    Accuracy: {user_data["accuracy"]}%\n
    _________________________________________________________________________________________________________________\n
    Kills: {user_data["kills"]}\n
    _________________________________________________________________________________________________________________\n
    Headshots: {user_data["headshots"]}\n
    _________________________________________________________________________________________________________________\n
    HS ratio: {user_data["hs"]}%\n
    _________________________________________________________________________________________________________________\n
    
    Weapon information:\n
    _________________________________________________________________________________________________________________\n
    First: Hits - {weap_data[0][0]}; left - {weap_data[0][1]}%; middle - {weap_data[0][2]}%; right - {weap_data[0][3]}\n
    _________________________________________________________________________________________________________________\n
    Sec: Hits - {weap_data[1][0]}; left - {weap_data[1][1]}%; middle - {weap_data[1][2]}%; right - {weap_data[1][3]}\n
    _________________________________________________________________________________________________________________\n
    Third: Hits - {weap_data[2][0]}; left - {weap_data[2][1]}%; middle - {weap_data[2][2]}%; right - {weap_data[2][3]}\n
    _________________________________________________________________________________________________________________\n
    """

    print(text)
    LOGGER.warning(text)


def main() -> None:
    """Runs the whole script and repeats after n minutes."""

    list_urls, list_weapon_urls = get_urls()  # Gives back a list of all URLs
    for i, url in enumerate(list_weapon_urls):  # Loop through all URLs

        html_data = get_user_weap_html(url)  # Each one will be processed by a function to obtain a needed data in HTML
        if not html_data:  # If function returns none, there's nothing to check and it skips to another player
            continue

        weapon_data = get_user_weap_stats(html_data)  # obtains data from HTML tables, information are in list
        user_data = get_user_main_stats(list_urls[i])  # Obtains main data about a user, gives back a dictionary

        if weapon_data and user_data:
            evaluate_user_data(weapon_data, user_data)  # Evaluates information based on data

    LOGGER.info("Script ended successfuly.")


if __name__ == "__main__":
    main()
