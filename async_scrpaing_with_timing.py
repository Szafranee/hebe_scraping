import ast
import asyncio
import time
from dataclasses import dataclass
from typing import List, Tuple
import aiohttp
from bs4 import BeautifulSoup
import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Product:
    """
    Represents a product with its details from Hebe website.
    """
    name: str
    price: str
    ingredients: str
    photo_url: str


async def extract_product_details(session: aiohttp.ClientSession, product_url: str, headers: dict) -> Tuple[str, str]:
    """
    Asynchronously extracts ingredients and photo URL from the product page.
    """
    try:
        async with session.get(product_url, headers=headers) as response:
            if response.status != 200:
                return 'Loading error', 'Loading error'

            html = await response.text()
            product_soup = BeautifulSoup(html, 'lxml')

            # Extract ingredients
            ingredients_tag = product_soup.find('div', id='product-ingredients')
            if ingredients_tag:
                ingredients_content = ingredients_tag.find('div', class_='ui-expandable__inner')
                ingredients = ingredients_content.get_text(strip=True) if ingredients_content else 'No ingredients information'
                # Use join-split method for better whitespace handling
                ingredients = ' '.join(ingredients.split())
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
    except Exception as e:
        logger.error(f"Error extracting product details: {e}")
        return 'Error loading', 'Error loading'


async def process_product(session: aiohttp.ClientSession, product_tile: BeautifulSoup, headers: dict) -> Product:
    """
    Process a single product tile and return a Product object.
    """
    try:
        # Extract product data from GTM attribute
        product_gtm_data = product_tile.attrs.get('data-product-gtm')
        if not product_gtm_data:
            return None

        product_data = ast.literal_eval(product_gtm_data)

        # Extract basic product information
        name = product_data.get('item_name', 'No name')
        price = product_data.get('price', 'No price')

        # Get product details URL
        product_link = product_tile.find('a', class_='product-tile__image').get('href')
        product_url = f'https://www.hebe.pl/{product_link}'

        # Get detailed product information
        ingredients, photo_url = await extract_product_details(session, product_url, headers)

        return Product(name, price, ingredients, photo_url)
    except Exception as e:
        logger.error(f"Error processing product: {e}")
        return None


async def scrape_page(session: aiohttp.ClientSession, page: int, headers: dict) -> Tuple[List[Product], float]:
    """
    Scrape a single page of products.

    Returns:
        Tuple containing list of products and time taken to scrape the page
    """
    BASE_URL = 'https://www.hebe.pl/pielegnacja-wlosow-szampony/'
    url = f'{BASE_URL}?start={page * 24}'

    start_time = time.time()

    try:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.error(f"Failed to fetch page {page}")
                return [], time.time() - start_time

            html = await response.text()
            soup = BeautifulSoup(html, 'lxml')
            product_tiles = soup.find_all('div', class_='product-tile')

            if not product_tiles:
                logger.info(f"No products found on page {page}")
                return [], time.time() - start_time

            # Process all products on the page concurrently
            tasks = [process_product(session, tile, headers) for tile in product_tiles]
            products = await asyncio.gather(*tasks)

            # Filter out None values (failed products)
            valid_products = [p for p in products if p is not None]

            elapsed_time = time.time() - start_time
            return valid_products, elapsed_time
    except Exception as e:
        logger.error(f"Error scraping page {page}: {e}")
        return [], time.time() - start_time


async def scrape_products(max_pages: int = None) -> List[Product]:
    """
    Main scraping function that coordinates the async scraping process.

    Args:
        max_pages: Optional maximum number of pages to scrape. If None, scrape all pages.
    """
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    connector = aiohttp.TCPConnector(limit=10)
    timeout = aiohttp.ClientTimeout(total=30)

    total_start_time = time.time()

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        all_products = []
        page = 0
        total_page_time = 0

        logger.info(f"Starting scraping process...")

        while True:
            # Check if we've reached the page limit
            if max_pages is not None and page >= max_pages:
                logger.info(f"Reached maximum number of pages ({max_pages})")
                break

            page_start_time = time.time()
            products, page_time = await scrape_page(session, page, HEADERS)
            total_page_time += page_time

            if not products:
                break

            all_products.extend(products)

            # Calculate statistics
            avg_product_time = page_time / len(products) if products else 0
            total_elapsed = time.time() - total_start_time
            estimated_remaining = (avg_product_time * (max_pages - page - 1) * 24) if max_pages else "unknown"

            logger.info(f"Page {page + 1}: {len(products)} products in {page_time:.2f}s "
                        f"({avg_product_time:.2f}s per product)")
            logger.info(f"Progress: {len(all_products)} total products, {total_elapsed:.2f}s elapsed, "
                        f"est. remaining: {estimated_remaining if isinstance(estimated_remaining, str) else f'{estimated_remaining:.2f}s'}")

            page += 1
            await asyncio.sleep(0.2)

        total_time = time.time() - total_start_time
        avg_page_time = total_page_time / page if page > 0 else 0
        avg_product_time = total_time / len(all_products) if all_products else 0

        logger.info(f"Scraping completed: {len(all_products)} products from {page} pages")
        logger.info(f"Total time: {total_time:.2f}s, Avg page time: {avg_page_time:.2f}s, "
                    f"Avg product time: {avg_product_time:.2f}s")

        return all_products


def save_products_to_csv(products: List[Product], filename: str = 'products.csv') -> None:
    """
    Saves the list of products to a CSV file.
    """
    start_time = time.time()

    with open(filename, 'w', encoding='utf-8') as file:
        file.write('Name;Price;Ingredients;Photo URL\n')
        for product in products:
            file.write(f'{product.name};{product.price};{product.ingredients};{product.photo_url}\n')

    elapsed = time.time() - start_time
    logger.info(f"Saved {len(products)} products to {filename} in {elapsed:.2f}s")


async def main():
    """
    Main entry point of the script.
    """
    try:
        script_start = time.time()

        # Scrape pages
        products = await scrape_products()

        # Save results
        save_products_to_csv(products)

        total_script_time = time.time() - script_start
        logger.info(f"Script completed in {total_script_time:.2f}s, scraped {len(products)} products")

    except Exception as e:
        logger.error(f"Script failed: {e}")


if __name__ == '__main__':
    asyncio.run(main())