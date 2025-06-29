import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
import re
import json

def scrape_detail_page(driver):
    """从详情页面提取名称、地址和经纬度"""
    try:
        # 等待详情页的关键元素加载
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'h1')))

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        name = 'N/A'
        address = 'N/A'
        lat, lon = None, None

        # 主要提取逻辑：从React组件的JSON数据中提取
        try:
            script_tag = soup.find('script', attrs={'data-component-name': 'LocationShow'})
            if script_tag:
                json_data = json.loads(script_tag.string)
                location_info = json_data.get('location', {})
                
                name = location_info.get('name', 'N/A')
                address = location_info.get('fullAddress', 'N/A')
                lat = location_info.get('latitude')
                lon = location_info.get('longitude')

                if lat and lon:
                    print(f"通过React组件JSON找到经纬度: lat={lat}, lon={lon}")
                else:
                    print("在React组件JSON中未找到经纬度。")
            else:
                print("未找到'LocationShow' React组件的script标签。")

        except Exception as e:
            print(f"通过React组件JSON提取数据时出错: {e}")
            # 如果主要方法失败，可以保留旧的h1和地址提取作为备用
            if name == 'N/A':
                name = soup.find('h1').get_text(strip=True) if soup.find('h1') else 'N/A'
            if address == 'N/A':
                 address_tag = soup.find('span', id='sidebarAddress')
                 address = address_tag.get_text(strip=True) if address_tag else 'N/A'


        # 如果主要方法失败，可以添加备用方案，但当前方法非常可靠，暂时省略

        return {'name': name, 'address': address, 'latitude': lat, 'longitude': lon}

    except TimeoutException:
        print("详情页面加载超时或未找到关键元素。")
        return None
    except Exception as e:
        print(f"解析详情页面时出错: {e}")
        return None

def save_to_geojson(data, filename):
    """将数据保存为GeoJSON格式"""
    features = []
    for item in data:
        # 确保经纬度存在且不为空
        if item.get('latitude') and item.get('longitude'):
            try:
                lat = float(item['latitude'])
                lon = float(item['longitude'])
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": {
                        "name": item.get('name', 'N/A'),
                        "address": item.get('address', 'N/A')
                    }
                }
                features.append(feature)
            except (ValueError, TypeError):
                print(f"警告: 无法解析经纬度，跳过此条记录: {item}")
                continue

    if not features:
        print("没有可用的地理数据来创建GeoJSON文件。")
        return

    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=4)
    print(f"数据也已保存到 {filename}, 共 {len(features)} 条含地理位置的记录。")


def main():
    """主函数"""
    base_url = "https://www.datacenters.com"
    
    start_url = input("请输入要爬取的完整URL (例如 'https://www.datacenters.com/locations/china/shanghai'): ")
    if not start_url:
        print("URL不能为空。")
        return

    if not start_url.startswith(f"{base_url}/locations/"):
        print(f"URL格式不正确，必须以 '{base_url}/locations/' 开头。")
        return

    # 从URL中提取地区路径用于生成文件名
    try:
        location_path = start_url.split('/locations/')[1]
        file_stem = location_path.replace('/', '_')
        csv_filename = f'{file_stem}_data_centers.csv'
        geojson_filename = f'{file_stem}_data_centers.geojson'
    except IndexError:
        print("无法从URL中提取地区路径。")
        return
    
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless') # 在调试时建议关闭无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument("--disable-dev-shm-usage") # 增加此项以防止资源限制问题
    options.add_argument("--disable-browser-side-navigation") # 增加此项以应对页面导航问题
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    
    all_locations = []
    visited_links = set() # 集合来存储访问过的详情页链接，防止重复

    try:
        print(f"正在导航到: {start_url}")
        driver.get(start_url)
        print("页面加载完成。")

        # 自动处理Cookie弹窗
        try:
            print("正在检查并处理Cookie弹窗...")
            # 等待Cookie弹窗中的“接受”按钮出现并点击
            accept_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"))
            )
            accept_button.click()
            print("已点击‘接受所有Cookie’按钮。")
            time.sleep(2) # 等待弹窗消失
        except TimeoutException:
            print("未找到Cookie弹窗，或已处理。")
        except Exception as e:
            print(f"处理Cookie弹窗时出错: {e}")
        
        while True:
            try:
                # 等待列表页面加载完成
                print("等待数据中心列表加载...")
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[class*="flex-col"][href*="/"]'))
                )
                print("列表加载成功。")
                time.sleep(3) # 等待页面稳定
            except TimeoutException:
                print("等待列表超时。检查页面是否正确加载。")
                # 增加调试信息
                print(f"当前URL: {driver.current_url}")
                print(f"页面标题: {driver.title}")
                break # 无法加载列表，退出循环

            # 找到当前页面所有数据中心的链接
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            item_links = soup.select('a[class*="flex-col"][href*="/"]')
            # 过滤掉已经访问过的链接
            detail_links = [link['href'] for link in item_links if link.select_one('div.text.font-medium') and link['href'] not in visited_links]

            if not detail_links:
                print("当前页面未找到新的数据中心链接。")
            else:
                print(f"在当前页面找到 {len(detail_links)} 个新的数据中心链接。")

            # 逐个访问详情页
            for i, link in enumerate(detail_links):
                visited_links.add(link) # 添加到已访问集合
                detail_url = f"{base_url}{link}"
                print(f"正在访问: {detail_url}")
                driver.get(detail_url)

                location_data = scrape_detail_page(driver)
                if location_data:
                    all_locations.append(location_data)
                    print(f"成功提取: {location_data['name']}")
                
                # 返回列表页
                print("正在返回列表页...")
                driver.back()
                # 等待列表页恢复
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[class*="flex-col"][href*="/"]'))
                )
                time.sleep(3) # 额外等待以确保页面稳定

            # 查找并点击下一页按钮
            try:
                # 定位当前激活的页码按钮
                active_button = driver.find_element(By.CSS_SELECTOR, 'button.Pagination__active__EK2e1')
                # 通过XPath找到它的下一个兄弟按钮（并且不是箭头按钮）
                next_button = active_button.find_element(By.XPATH, './following-sibling::button[not(contains(@class, "Pagination__symbol__KHv6r"))]')
                
                print(f"找到下一页按钮: {next_button.text}。正在点击...")
                driver.execute_script("arguments[0].click();", next_button)
                print("正在翻页...")
            except NoSuchElementException:
                print("没有更多页码按钮了，爬取结束。")
                break
            except Exception as e:
                print(f"翻页时出现未知错误: {e}")
                break

    except Exception as e:
        print(f"在主循环中发生错误: {e}")
    finally:
        print("正在关闭浏览器驱动...")
        driver.quit()

    if all_locations:
        # 以防万一，去重
        unique_locations = [dict(t) for t in {tuple(d.items()) for d in all_locations}]
        df = pd.DataFrame(unique_locations)
        df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        print(f"\n数据已保存到 {csv_filename}, 共 {len(unique_locations)} 条记录。")
        
        # 新增：保存为GeoJSON
        save_to_geojson(unique_locations, geojson_filename)
    else:
        print("\n未能爬取到任何数据。")

if __name__ == '__main__':
    main()
