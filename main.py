from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
from pydantic import BaseModel
import asyncio
import httpx
import time
import concurrent.futures
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://kikisan.pages.dev",
    "https://kikisan.site",
    "https://www.kikisan.site",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DataRequest(BaseModel):
    pages: int
    keyword: str
    userAgent: str


@app.post("/asyncseleniumhttpx")
def index(data: DataRequest):
    try:
        headers = {"User-Agent": data.userAgent}
        start_time = time.time()
        loop = main(headers, data.keyword, data.pages)
        end_time = time.time()
        print(
            f"Berhasil mengambil {len(loop)} produk dalam {end_time - start_time} detik."
        )
        return loop
    except Exception as e:
        return e


def main(headers, keyword, pages):
    product_soup = []

    # loop = asyncio.get_event_loop()
    # tasks = [
    #     loop.create_task(
    #         scrape(f"https://www.tokopedia.com/search?q={keyword}&page={page}")
    #     )
    #     for page in range(1, pages + 1)
    # ]
    # for task in asyncio.as_completed(tasks):
    #     page_product_soup = await task
    #     product_soup.extend(page_product_soup)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(scrape, keyword, page) for page in range(1, pages + 1)
        ]
        for future in concurrent.futures.as_completed(futures):
            soup_produk = future.result()
            if soup_produk:
                product_soup.extend(soup_produk)
    tasks = []
    with httpx.Client() as session:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            for i in product_soup:
                tasks.append(executor.submit(scrape_page, i, session, headers))

        combined_data = []
        for task in concurrent.futures.as_completed(tasks):
            array = task.result()
            if array:
                combined_data.append(array)
        return combined_data


def scrape(keyword, page):
    soup_produk = []
    # chrome_options = Options()
    # chrome_options.add_argument("--headless")

    driver = webdriver.Chrome()
    try:
        # await asyncio.sleep(2)
        driver.get(f"https://www.tokopedia.com/search?q={keyword}&page={page}")
        print("Menunggu reload...")
        time.sleep(
            5
        )  # Tunggu beberapa detik untuk memastikan halaman telah selesai dimuat

        # Scrolling
        prev_height = driver.execute_script("return document.documentElement.scrollTop")
        while True:
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)  # Tunggu beberapa detik setelah melakukan scroll
            curr_height = driver.execute_script(
                "return document.documentElement.scrollTop"
            )
            if prev_height == curr_height:
                break
            prev_height = curr_height
            print("Scrolling...")
        content = driver.page_source
        soup = BeautifulSoup(content, "html.parser")
        product_selectors = [
            ("div", {"class": "css-kkkpmy"}),
            ("div", {"class": "css-llwpbs"}),
        ]
        for selector in product_selectors:
            tag, attrs = selector
            products = soup.find_all(tag, attrs)
            for product in products:
                link = product.find("a", {"class": "pcv3__info-content css-gwkf0u"})
                if link:
                    soup_produk.append(product)
        print(f"Berhasil scrape data dari halaman {page}.")
        driver.close()
        return soup_produk
    except Exception as e:
        print(f"Terjadi kesalahan saat mengakses halaman {page}: {str(e)}")


def scroll(page, scroll_amount):
    try:
        prev_height = page.evaluate("document.documentElement.scrollTop")
        while True:
            page.wait_for_selector(".css-974ipl", timeout=1800000)
            page.evaluate(f"window.scrollBy(0, {scroll_amount});")
            curr_height = page.evaluate("document.documentElement.scrollTop")
            if prev_height == curr_height:
                break
            prev_height = curr_height
            print("Scrolling...")
    except Exception as e:
        print(f"Terjadi kesalahan saat Scrolling: {str(e)}")


async def scrape_produk(product_soup, headers, session):
    tasks = [scrape_page(soup, headers, session) for soup in product_soup]
    tasks = await asyncio.gather(*tasks)
    return tasks


def scrape_page(soup, session, headers):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        href = soup.find("a")["href"]
        link_parts = href.split("r=")
        r_part = link_parts[-1]
        link_part = r_part.split("&")
        r_part = link_part[0]
        new_link = f"{r_part.replace('%3A', ':').replace('%2F', '/')}"
        new_link = new_link.split("%3FextParam")[0]
        new_link = new_link.split("%3Fsrc")[0]
        new_link = new_link.split("?extParam")[0]
        tasks = []

        # Menambahkan tugas scraping data produk ke dalam daftar tasks
        product_task = executor.submit(data_product, soup, new_link, session, headers)
        tasks.append(product_task)

        # Menambahkan tugas scraping data toko ke dalam daftar tasks
        shop_task = executor.submit(
            data_shop, "/".join(new_link.split("/")[:-1]), session, headers
        )
        tasks.append(shop_task)

        # Mengumpulkan hasil scraping
        results = {}
        for future in concurrent.futures.as_completed(tasks):
            results.update(future.result())
        # results.update(executor.submit(data_product, soup, new_link, session, headers))
        return results


def data_product(soup_produk, product_link, session, headers):
    try_count = 0
    while try_count < 5:
        try:
            response = session.get(product_link, headers=headers, timeout=30.0)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            data_to_scrape = {
                "link_product": "",
                "product_name": ("h1", {"class": "css-1os9jjn"}),
                "product_price": ("div", {"class": "price"}),
                "product_terjual": (
                    "span",
                    {"class": "prd_label-integrity css-1duhs3e"},
                ),
                "product_rating": (
                    "span",
                    {"class": "prd_rating-average-text css-t70v7i"},
                ),
                "product_diskon": (
                    "div",
                    {"class": "prd_badge-product-discount css-1qtulwh"},
                ),
                "price_ori": (
                    "div",
                    {"class": "prd_label-product-slash-price css-1u1z2kp"},
                ),
                "product_items": ("div", {"class": "css-1b2d3hk"}),
                "product_detail": ("li", {"class": "css-bwcbiv"}),
                "product_keterangan": ("span", {"class": "css-168ydy0 eytdjj01"}),
            }

            results = {}

            for key, value in data_to_scrape.items():
                if key == "product_detail":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    results[key] = [element.text.strip() for element in elements]
                elif key == "product_items":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    if elements:
                        for key_element in elements:
                            items = key_element.find_all(
                                "div", {"class": "css-1y1bj62"}
                            )
                            kunci = (
                                key_element.find(
                                    "p", {"class": "css-x7tz35-unf-heading e1qvo2ff8"}
                                )
                                .text.strip()
                                .split(":")[0]
                            )
                            results[kunci] = [
                                item.text.strip()
                                for item in items
                                if item.text.strip()
                                != ".css-1y1bj62{padding:4px 2px;display:-webkit-inline-box;display:-webkit-inline-flex;display:-ms-inline-flexbox;display:inline-flex;}"
                            ]
                    else:
                        results[key] = None
                elif key == "link_product":
                    results[key] = product_link
                elif (
                    key == "product_terjual"
                    or key == "product_rating"
                    or key == "product_diskon"
                    or key == "price_ori"
                ):
                    tag, attrs = value
                    element = soup_produk.find(tag, attrs)
                    if element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
                else:
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    if element:
                        text = element.get_text(
                            separator="<br>"
                        )  # Gunakan separator '\n' untuk menambahkan baris baru
                        results[key] = text.strip()
                    else:
                        results[key] = None
            print(f"Berhasil scrape data produk dari halaman {product_link}")
            return results

        except (httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError):
            try_count += 1
            print(f"Koneksi ke {product_link} timeout. Mencoba lagi...")
    else:
        print(
            f"Gagal melakukan koneksi ke {product_link} setelah mencoba beberapa kali."
        )
        return {}


def data_shop(shop_link, session, headers):
    try_count = 0
    while try_count < 5:
        try:
            response = session.get(shop_link, headers=headers, timeout=30.0)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            data_to_scrape = {
                "link_shop": "",
                "shop_name": ("h1", {"class": "css-1g675hl"}),
                "shop_status": ("span", {"data-testid": "shopSellerStatusHeader"}),
                "shop_location": ("span", {"data-testid": "shopLocationHeader"}),
                "shop_info": ("div", {"class": "css-6x4cyu e1wfhb0y1"}),
            }

            results = {}

            for key, value in data_to_scrape.items():
                if key == "link_shop":
                    results[key] = shop_link
                elif key == "shop_status":
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    time = soup.find("strong", {"class": "time"})
                    if time:
                        waktu = time.text.strip()
                        status = element.text.strip()
                        results[key] = status + " " + waktu
                    elif element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
                elif key == "shop_info":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    key = ["rating_toko", "respon_toko", "open_toko"]
                    ket = soup.find_all(
                        "p", {"class": "css-1dzsr7-unf-heading e1qvo2ff8"}
                    )
                    i = 0
                    for item, keterangan in zip(elements, ket):
                        if item and keterangan:
                            results[key[i]] = (
                                item.text.replace("\u00b1", "").strip()
                                + " "
                                + keterangan.text.strip()
                            )
                        else:
                            results[key[i]] = None
                        i += 1
                else:
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    if element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
            print(f"Berhasil scrape data toko dari halaman {shop_link}")
            return results

        except (httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError):
            try_count += 1
            print(f"Koneksi ke {shop_link} timeout. Mencoba lagi...")
    else:
        print(f"Gagal melakukan koneksi ke {shop_link} setelah mencoba beberapa kali.")
        return {}