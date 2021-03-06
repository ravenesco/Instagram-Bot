import logging
import random
from time import sleep
from datetime import datetime

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.wait import WebDriverWait

import config
from filter import PostFilter
from post_parser import parse_explore
from strategy import RunForeverStrategy
from tracker import post_tracker
from utils import rand_wait_sec

logging.basicConfig(handlers=[logging.StreamHandler()],
                    level=logging.INFO,
                    format='%(asctime)s [%(levelname).4s] %(message)s',
                    datefmt='%a %d %H:%M:%S')

logger = logging.getLogger()


class AutoLikeBot:
    def __init__(self, driver: WebDriver, post_filter=PostFilter(), running_strategy=RunForeverStrategy()):
        self.driver = driver
        self.post_filter = post_filter
        self.running_strategy = running_strategy

    def __enter__(self):
        if not config.SKIP_LOGIN:
            self.log_in()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.driver.quit()
        logger.info(post_tracker.stats)
        return None

    def wait_until(self, condition, timeout=5):
        WebDriverWait(self.driver, timeout).until(condition)

    def log_in(self):
        self.driver.get("https://www.instagram.com/")
        try:
            self.wait_until(ec.presence_of_element_located((By.NAME, 'username')))

            try:
                self.driver.find_element_by_name('username').send_keys(config.USERNAME)
                self.driver.find_element_by_name('password').send_keys(config.PASSWORD)
                login_button = self.driver.find_element_by_xpath(
                    '//*[@id="react-root"]/section/main/article/div[2]/div[1]/div/form/div/div[4]/button')
                self.driver.execute_script("arguments[0].click();", login_button)

            except NoSuchElementException as e:
                logger.warning(f"Could not find element. Error: {e}")
                return

        except TimeoutException:
            pass

        try:
            # Remember this browser prompt
            prompt_button = self.driver.find_element_by_xpath(
                '//*[@id="react-root"]/section/main/div/div/div/section/div/button')
            self.driver.execute_script("arguments[0].click();", prompt_button)
        except NoSuchElementException:
            pass

        try:
            # Turn on notifications prompt
            skip_notifications_button = self.driver.find_element_by_xpath("/html/body/div[4]/div/div/div/div[3]/button[2]")
            self.driver.execute_script("arguments[0].click();", skip_notifications_button)
            logger.debug("Skipping turn on notifications")
        except NoSuchElementException:
            pass

        self.wait_until(ec.presence_of_element_located((By.CLASS_NAME, 'C3uDN')))

    def load_pre_from_url(self, url):
        self.open_and_switch_to_tab(url)
        try:
            self.wait_until(ec.presence_of_element_located((By.TAG_NAME, 'pre')), timeout=7)
            return self.driver.find_element_by_tag_name('pre').text
        finally:
            self.close_and_open_tab()

    def open_and_switch_to_tab(self, url):
        handles = self.driver.window_handles
        self.driver.execute_script(f"window.open('{url}');")
        # Index based
        self.driver.switch_to.window(self.driver.window_handles[len(handles)])

    def close_and_open_tab(self, tab_index=0):
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[tab_index])

    def fetch_posts_from_explore(self, max_id=0):
        text = self.load_pre_from_url(
            f"https://www.instagram.com/explore/grid/?is_prefetch=false&omit_cover_media=false&module=explore_popular&use_sectional_payload=true&cluster_id=explore_all%3A0&include_fixed_destinations=true&max_id={max_id}")
        return parse_explore(text)

    def fetch_followings_list(self):
        followings_list = {}
        userurl = f"https://www.instagram.com/{config.TARGET_USERNAME}/"

        self.driver.get(userurl)

        followings_count = int(self.driver.find_elements_by_class_name('g47SY')[2].text)
        followings_button = self.driver.find_element_by_xpath('/html/body/div[1]/section/main/div[1]/header/section/ul/li[3]/a')
        self.driver.execute_script("arguments[0].click();", followings_button)
        self.wait_until(ec.presence_of_element_located((By.CLASS_NAME, 'isgrP')), timeout=7)
        fBody = self.driver.find_element_by_class_name('isgrP')

        scrolling_times = (followings_count / 4) + 5
        scroll = 0

        # Scroll the list of followings down to the bottom so all posts appear in DOM
        # Initial scroll makes classes of followings change
        self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;', fBody)

        while scroll < scrolling_times:
            fList = self.driver.find_elements_by_class_name('enpQJ')

            for following in fList:
                try:
                    following = following.text
                    following = following.split('\n')

                    username = following[0]
                    name = following[1]

                    followings_list[username] = name
                except:
                    continue

            self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].offsetHeight;', fBody)
            sleep(2)
            scroll += 1

        return followings_list

    def fetch_posts_links_from_profile(self, userurl):
        self.open_and_switch_to_tab(userurl)
        post_links_list = set()

        try:
            self.wait_until(ec.presence_of_element_located((By.CLASS_NAME, 'v1Nh3')), timeout=7)
            # Scroll the page down to the bottom so all posts appear in DOM
            scrolldown = self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);var scrolldown=document.body.scrollHeight;return scrolldown;")
            match = False
            while(match == False):
                try:
                    last_count = scrolldown
                    sleep(3)
                    scrolldown = self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);var scrolldown=document.body.scrollHeight;return scrolldown;")
                    if last_count == scrolldown:
                        match=True

                    self.driver.execute_script("window.scrollTo(0,document.body.scrollHeight)")
                    posts = self.driver.find_elements_by_class_name('v1Nh3')

                    for post in posts:
                        post_link = post.find_element_by_xpath('.//a')
                        post_links_list.add(post_link.get_attribute('href'))

                except Exception as e:
                    print(type(e))    # the exception instance
                    print(e.args)     # arguments stored in .args
                    print(e)          # __str__ allows args to be printed directly,
                                      # but may be overridden in exception subclasses
                    pass
        except Exception as e:
            print(type(e))    # the exception instance
            print(e.args)     # arguments stored in .args
            print(e)          # __str__ allows args to be printed directly,
                              # but may be overridden in exception subclasses
            return post_links_list
        finally:
            self.close_and_open_tab()
        return post_links_list

    def like_post(self, post):
        self.open_and_switch_to_tab(post.post_link)
        try:
            self.wait_until(ec.presence_of_element_located((By.CLASS_NAME, 'fr66n')))
            like_button = self.driver.find_element_by_xpath('//*[@class="fr66n"]/button')
            self.driver.execute_script("arguments[0].click();", like_button)

            post_tracker.liked_post(post)
            logger.info(f"Liked {post}")
            rand_wait_sec()
            return True

        # Post might get removed
        except (NoSuchElementException, TimeoutException):
            return False
        finally:
            self.close_and_open_tab()

    def like_post_by_link(self, post_link):
        self.open_and_switch_to_tab(post_link)
        try:
            self.wait_until(ec.presence_of_element_located((By.CLASS_NAME, 'fr66n')))
            like_button = self.driver.find_element_by_xpath('//*[@class="fr66n"]/button')
            self.driver.execute_script("arguments[0].click();", like_button)

            logger.info(f"Liked {post_link}")
            rand_wait_sec()
            return True

        # Post might get removed
        except (NoSuchElementException, TimeoutException):
            return False
        finally:
            self.close_and_open_tab()

    def like_from_explore(self):
        max_id = 0

        while True:
            try:
                posts = self.fetch_posts_from_explore(max_id)
            except TimeoutException:
                continue
            random.shuffle(posts)
            for post in posts:
                if self.post_filter.should_like(post):
                    self.like_post(post)

                    if not self.running_strategy.should_continue_run():
                        return
                else:
                    post_tracker.skipped_post(post)

            max_id += 1

    def like_followings_list(self):
        followings_list = self.fetch_followings_list()

        for username, _ in followings_list.items():
            try:
                self.like_all_posts_on_profile(username)
            except TimeoutException:
                continue

    def like_all_posts_on_profile(self, username):
        try:
            userurl = f"https://www.instagram.com/{username}/"
            post_links = self.fetch_posts_links_from_profile(userurl)
        except TimeoutException:
            return
        print("Post Links:")
        i = 1
        for link in post_links:
            print(f"{i}.    {link}")
            i += 1
            self.like_post_by_link(link)

    def list_all_followings(self):
        followings_list = self.fetch_followings_list()
        filename = config.TARGET_USERNAME + "_" + datetime.now().strftime("%d-%m-%Y_%H-%M-%S") + ".txt"

        with open(filename, "a", encoding="utf-8") as f_out:
            for username, name in followings_list.items(): 
                f_out.write('%s    %s\n' % (username, name))
