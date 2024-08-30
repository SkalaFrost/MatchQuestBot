import asyncio
import random
import string
from time import time
from urllib.parse import unquote, quote
from colorama import Fore, Style, init
import aiohttp
import json
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw import types
from .agents import generate_random_user_agent
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers
from .helper import format_duration
from datetime import datetime

class Tapper:
    def __init__(self, tg_client: Client):
        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None
        self.rf_token = None
        self.session_ug_dict = self.load_user_agents() or []

        headers['User-Agent'] = self.check_user_agent()

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type='android', browser_type='chrome')

    def info(self, message):
        from bot.utils import info
        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug
        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning
        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error
        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical
        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success
        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"

        if not any(session['session_name'] == self.session_name for session in self.session_ug_dict):
            user_agent_str = generate_random_user_agent()

            self.session_ug_dict.append({
                'session_name': self.session_name,
                'user_agent': user_agent_str})

            with open(user_agents_file_name, 'w') as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)

            logger.success(f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully")

            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"

        try:
            with open(user_agents_file_name, 'r') as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data

        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")

        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")

        return []

    def check_user_agent(self):
        load = next(
            (session['user_agent'] for session in self.session_ug_dict if session['session_name'] == self.session_name),
            None)

        if load is None:
            return self.save_user_agent()

        return load

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            if settings.REF_ID == '':
                self.start_param = 'd5747e9a44b78865a034716d1d943d6a'
            else:
                self.start_param = settings.REF_ID

            peer = await self.tg_client.resolve_peer('MatchQuestBot')
            InputBotApp = types.InputBotAppShortName(bot_id=peer, short_name="app")

            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=peer,
                app=InputBotApp,
                platform='android',
                write_allowed=True,
                start_param=self.start_param
            ))

            auth_url = web_view.url
            #print(auth_url)
            tg_web_data = unquote(
                string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])

            try:
                if self.user_id == 0:
                    information = await self.tg_client.get_me()
                    self.user_id = information.id
                    self.first_name = information.first_name or ''
                    self.last_name = information.last_name or ''
                    self.username = information.username or ''
            except Exception as e:
                print(e)

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    def parse_user_data(self,tg_web_data):
        user_data_list = []
        user_data_encoded = tg_web_data.split('user=')[1].split('&')[0]
        user_data_json = unquote(user_data_encoded)
        user_data = json.loads(user_data_json)
        return user_data
    
    async def get_token(self, http_client: aiohttp.ClientSession, line, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/user/login'
        payload = {
            "uid": user_data["id"],
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
            "username": user_data.get("username", ""),
            "tg_login_params": line
        }
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Your query is incorrect")
            return None

    async def get_profile(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/user/profile'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def get_farming_reward(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/reward'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def get_ref_reward(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/invite/balance'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def claim_ref_reward(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/invite/claim'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def claim_farming_reward(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/reward/claim'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def start_farming(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/reward/farming'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def get_task(self, http_client: aiohttp.ClientSession, user_data):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/task/list'
        payload = {"uid": user_data["id"]}
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                res =  await response.json()
                todo_task = []
                for task,items in res["data"].items():
                    todo_task.extend(items)
                return todo_task
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def complete_task(self, http_client: aiohttp.ClientSession, user_data, task_name):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/task/complete'
        payload = {
            "uid": user_data["id"],
            "type": task_name
        }
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def claim_task(self, http_client: aiohttp.ClientSession, user_data, task_name):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/point/task/claim'
        payload = {
            "uid": user_data["id"],
            "type": task_name
        }
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def check_ticket(self, http_client: aiohttp.ClientSession):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/game/rule'
        try:
            async with http_client.get(url) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def play_game(self, http_client: aiohttp.ClientSession):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/game/play'
        try:
            async with http_client.get(url) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def claim_game(self, http_client: aiohttp.ClientSession, game_id, point):
        url = 'https://tgapp-api.matchain.io/api/tgapp/v1/game/claim'
        payload = {
            "game_id": game_id,
            "point": point
        }
        try:
            async with http_client.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None
    
    async def check_quiz(self, http_client: aiohttp.ClientSession):
        url = "https://tgapp-api.matchain.io/api/tgapp/v1/daily/quiz/progress"
        try:
            async with http_client.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    async def submit_quiz(self, http_client: aiohttp.ClientSession, selected_item):
        url = "https://tgapp-api.matchain.io/api/tgapp/v1/daily/quiz/submit"
        payload = {"answer_result": selected_item}
        try:
            async with http_client.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            print(f"Request Error: {e}")
            return None
        except json.JSONDecodeError:
            print(f"JSON Decode Error: Invalid token")
            return None

    def format_balance(self, balance):
        if balance < 1000:
            return str(balance)
        return f"{balance // 1000}"
    
    def convert_ts(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return hours, minutes, seconds
    
    async def run(self, proxy: str | None) -> None:
        access_token_created_time = 0
        access_token = None
        refresh_token = None

        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        init_data = await self.get_tg_web_data(proxy=proxy)

       
        while True:
            try:
                user_data = self.parse_user_data(init_data)
                get_token_response = await self.get_token(http_client=http_client,line=init_data,user_data=user_data)
                if get_token_response:
                    access_token = get_token_response['data'].get('token')
                    http_client.headers["Authorization"] = f"{access_token}"
                    
                    answer_result = []
                    quizlist = await self.check_quiz(http_client=http_client)
                    if quizlist and quizlist.get('msg', 'Available') == 'Available':
                        for quiz in quizlist.get('data', []):
                            quiz_title = quiz.get('title', 'Unknown')
                            self.info(f"[ Quiz ]: Finding Answer for {quiz_title}")
                            quiz_id = quiz.get('Id', 'Unknown')
                            answer = ''
                            for answer in quiz.get('items', []):
                                if answer.get('is_correct', False):
                                    # example {"quiz_id":20,"selected_item":"B","correct_item":"B"}
                                    self.info(f"[ Quiz ]: Answer found : {answer['number']}")
                                    answer_result.append({"quiz_id": quiz_id, "selected_item": answer['number'], "correct_item": answer['number']})
                                    break
                    elif quizlist and quizlist.get('msg', 'Available') == 'Already answered today':
                        self.info(f"[ Quiz ]: Quiz already answered today")
                    else:
                        self.info(f"[ Quiz ]: Failed to get quiz information")

                    await asyncio.sleep(random.randint(2,10))
                    if answer_result:
                        submit_quiz_response = await self.submit_quiz(http_client=http_client, selected_item=answer_result)
                        if submit_quiz_response and submit_quiz_response.get('msg', 'NOTOK') == 'OK':
                            self.success(f"[ Quiz ]: Quiz successfully answered")
                        else:
                            self.info(f"[ Quiz ]: Failed to submit quiz answers")
                    else:
                        self.info(f"[ Quiz ]: No quiz found")

                    profile = await self.get_profile(user_data = user_data,http_client=http_client)
                    if profile is None or 'data' not in profile:
                        self.info(f"[ Profile ]: Data could not be retrieved!")
                        await asyncio.sleep(5)
                        return
                    
                    balance = profile['data'].get('Balance', 0)
                    invite_count = profile['data'].get('invite_count', 0)
                    balance_view = self.format_balance(balance)
                    self.info(f"[ Balance ]: {balance_view}")
                    self.info(f"[ Total Invites ]: {invite_count}")

                    farming_balance = await self.get_farming_reward(user_data = user_data,http_client=http_client)
                    if farming_balance is None or 'data' not in farming_balance:
                        self.error(f"[ Farming ]: Data could not be retrieved!")
                    else:
                        claim_balance = int(self.format_balance(farming_balance['data']['reward']))  # Convert to integer
                        claim_in = farming_balance.get('data', {}).get('next_claim_timestamp')
                        ts = datetime.now().timestamp() * 1000
                        time_remaining = max(0, claim_in - ts)

                        second = int(time_remaining / 1000)
                        hours, minutes, seconds = self.convert_ts(second)
                        self.info(f"[ Farming ]: Claim time {hours} Hours {minutes} Minutes")

                        if time_remaining == 0:
                            claim_farming = await self.claim_farming_reward(user_data = user_data,http_client=http_client)
                            if claim_farming:
                                self.success(f"[ Farming ]: Claimed {claim_balance} Points   ")
                                self.info(f"[ Farming ]: Starting farming..")
                                start_farming_response = await self.start_farming(user_data = user_data,http_client=http_client)
                                if start_farming_response:
                                    self.info(f"[ Farming ]: Farming started!")
                                else:
                                    self.error(f"[ Farming ]: Farming could not start!")
                            else:
                                self.error(f"[ Farming ]: Claim failed")
                        else:
                            self.info(f"[ Farming ]: Starting farming..")
                            start_farming_response = await self.start_farming(user_data = user_data,http_client=http_client)
                            if start_farming_response:
                                self.info(f"[ Farming ]: Farming started!")
                            else:
                                self.error(f"[ Farming ]: Farming could not start!")

                        self.info(f"[ Ref Balance ]: Checking..")
                        await asyncio.sleep(2)
                        check_ref_balance = await self.get_ref_reward(user_data = user_data,http_client=http_client)
                        if check_ref_balance is None or 'data' not in check_ref_balance:
                            self.error(f"[ Ref Balance ]: Data could not be retrieved!")
                        else:
                            balance = check_ref_balance['data'].get('balance', 0)
                            balance_view = self.format_balance(balance)
                            self.success(f"[ Ref Balance ]: Reward {balance_view} Points          ")
                            if int(balance_view) > 0:
                                claim_ref = await self.claim_ref_reward(user_data = user_data,http_client=http_client)
                                if claim_ref:
                                    balance_claim = claim_ref.get('data')
                                    balance_claim_view = self.format_balance(balance_claim)
                                    self.success(f"[ Ref Balance ]: Claimed {balance_claim_view} Points ")
                                else:
                                    self.error(f"[ Ref Balance ]: Ref balance claim failed!          ")

                        if settings.AUTO_TASK:
                            self.info(f"[ Task ]: Checking..")
                            get_task_list = await self.get_task(user_data = user_data,http_client=http_client)
                            if get_task_list:
                                for task in get_task_list:
                                    if not task['complete']:
                                        self.info(f"[ Task ]: Completing task {task['name']}")
                                        await asyncio.sleep(random.randint(2,10))
                                        complete_task_result = await self.complete_task(user_data = user_data, task_name= task['name'],http_client=http_client)
                                        if complete_task_result:
                                            result = complete_task_result.get('data', False)
                                            if result:
                                                self.success(f"[ Task ]: Claiming task {task['name']}    ")
                                                await asyncio.sleep(random.randint(2,10))
                                                claim_task_result = await self.claim_task(user_data = user_data, task_name= task['name'],http_client=http_client)
                                                if claim_task_result:
                                                    self.info(f"[ Task ]: Task completed and claimed {task['name']}    ")
                                                else:
                                                    self.info(f"[ Task ]: Task claim failed {task['name']}       ")
                                            else:
                                                self.info(f"[ Task ]: Task claim failed {task['name']}       ")
                                        else:
                                            self.info(f"[ Task ]: Task not completed {task['name']} ")
                            else:
                                self.info(f"[ Task ]: Task list could not be retrieved          ")
                                
                        self.info(f"[ Game ]: Checking ticket..")
                        await asyncio.sleep(2)
                        ticket_response = await self.check_ticket(http_client=http_client)

                        if ticket_response:
                            total_ticket = ticket_response.get('data', {}).get('game_count')
                            self.info(f"[ Game ]: {total_ticket} Ticket ")

                            if settings.AUTO_PLAY_GAME:
                                while total_ticket > 0:
                                    self.info(f"[ Game ]: Playing game..")
                                    await asyncio.sleep(2)
                                    get_game_id = await self.play_game(http_client=http_client)

                                    if get_game_id:
                                        game_id = get_game_id.get('data', {}).get('game_id')
                                        if game_id:
                                            max_score = random.randint(*settings.POINTS)
                                            await asyncio.sleep(random.randint(30,50))
                                            game_result = await self.claim_game(game_id=game_id, point=max_score,http_client=http_client)
                                            
                                            if game_result.get('code') == 200:
                                                self.success(f"[ Game ]: Game played successfully | Score: {max_score} Points     ")
                                                await asyncio.sleep(2)
                                            else:
                                                self.error(f"[ Game ]: Game could not be played,{game_result}")
                                                await asyncio.sleep(2)

                                            check_remaining_tickets = await self.check_ticket(http_client=http_client)
                                            total_ticket = check_remaining_tickets.get('data', {}).get('game_count')  # Update total_ticket
                                            if total_ticket > 0:
                                                continue
                                            else:
                                                self.info(f"[ Game ]: No more tickets left        ")
                                        else:
                                            self.error(f"[ Game ]: Game could not be played ")
                        else:
                            self.info(f"[ Game ]: Ticket could not be retrieved")
                self.info(f"[ Farming ]: Sleeping {second}s")
                await asyncio.sleep(delay=second)
            
            except Exception as error:
                logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Unknown error: {error}")
                await asyncio.sleep(delay=3)

async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
