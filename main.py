import requests


def main():
    res = requests.get('https://www.google.com') # res means response
    print(res.text)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()