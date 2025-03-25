import ast
from dataclasses import dataclass
from random import randint
from time import sleep
from typing import List, Optional

import requests
from bs4 import BeautifulSoup, Tag

@dataclass
class Product:
    """
    Represents a product with its details from Hebe website.
    """
    name: str
    price: str
    ingredients: str
    photo_url: str


def extract_product_details(product_soup: BeautifulSoup) -> tuple[str, str]:
    """
    Extracts ingredients and photo URL from the product page.

    Args:
        product_soup: BeautifulSoup object of the product page

    Returns:
        Tuple containing ingredients and photo URL
    """
    # Extract ingredients
    ingredients_tag = product_soup.find('div', id='product-ingredients')
    if ingredients_tag:
        ingredients_content = ingredients_tag.find('div', class_='ui-expandable__inner')
        ingredients = ingredients_content.get_text(strip=True) if ingredients_content else 'No ingredients information'
    else:
        ingredients = 'No ingredients information'

    # Extract photo URL
    photo_url = 'No photo available'
    photo_container = product_soup.find('div', class_='carousel-product__inner')
    if photo_container:
        img_tag = photo_container.find('img')
        if img_tag:
            photo_url = img_tag.attrs.get('data-srcset', 'No photo available')

    return ingredients, photo_url


def scrape_products() -> List[Product]:
    """
    Scrapes product information from Hebe website.

    Returns:
        List of Product objects containing scraped data
    """
    BASE_URL = 'https://www.hebe.pl/pielegnacja-wlosow-szampony/'
    HEADERS = {'User-Agent': 'Mozilla/5.0'}

    page = 0
    first_product_id = ''
    products_list = []

    while True:
        # Construct URL for current page
        current_url = f'{BASE_URL}?start={page * 24}'
        response = requests.get(current_url, headers=HEADERS)

        if response.status_code != 200:
            print('Error: Failed to fetch page')
            break

        soup = BeautifulSoup(response.text, 'lxml')
        product_tiles = soup.find_all('div', class_='product-tile')

        if not product_tiles:
            print('End of pages reached.')
            break

        print(f'\nPage {page + 1}: Found {len(product_tiles)} products.\n')

        for product_tile in product_tiles:
            # Extract product data from GTM attribute
            product_gtm_data = product_tile.attrs.get('data-product-gtm')
            if not product_gtm_data:
                continue

            product_data = ast.literal_eval(product_gtm_data)
            current_product_id = product_data.get('item_id')

            # Check if we've completed a full cycle of products
            if not first_product_id:
                first_product_id = current_product_id
            elif current_product_id == first_product_id:
                return products_list

            # Extract basic product information
            name = product_data.get('item_name', 'No name')
            price = product_data.get('price', 'No price')

            # Get product details URL
            product_link = product_tile.find('a', class_='product-tile__image').get('href')
            product_url = f'https://www.hebe.pl/{product_link}'

            # Fetch and parse product details page
            product_response = requests.get(product_url, headers=HEADERS)

            if product_response.status_code == 200:
                product_soup = BeautifulSoup(product_response.text, 'lxml')
                ingredients, photo_url = extract_product_details(product_soup)
            else:
                ingredients, photo_url = 'Loading error', 'Loading error'

            # Create and store product object
            product = Product(name, price, ingredients, photo_url)
            products_list.append(product)

        page += 1
        # Add small delay between requests
        # sleep(randint(1, 3))

    return products_list


def save_products_to_csv(products: List[Product], filename: str = 'products.csv') -> None:
    """
    Saves the list of products to a CSV file.

    Args:
        products: List of Product objects to save
        filename: Name of the output CSV file
    """
    with open(filename, 'w', encoding='utf-8') as file:
        file.write('Name; Price; Ingredients; Photo URL\n')
        for product in products:
            file.write(f'{product.name}; {product.price}; {product.ingredients}; {product.photo_url}\n')


if __name__ == '__main__':
    products_list = scrape_products()
    save_products_to_csv(products_list)