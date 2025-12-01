import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from telegram import Bot
from telegram.constants import ParseMode
import aiohttp

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8326225213:AAGsScRkwKKGipb_z_57vfGeDBw6Iz-hkdA'
CHANNEL_USERNAME = '@Ton24Price'

APIS = [
    {
        'name': 'KuCoin',
        'url': 'https://api.kucoin.com/api/v1/market/stats?symbol=TON-USDT',
        'parse': lambda d: (Decimal(d['data']['last']), Decimal(d['data']['changeRate']) * 100)
    },
    {
        'name': 'OKX',
        'url': 'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT',
        'parse': lambda d: (Decimal(d['data'][0]['last']), ((Decimal(d['data'][0]['last']) - Decimal(d['data'][0]['open24h'])) / Decimal(d['data'][0]['open24h'])) * 100)
    },
    {
        'name': 'Gate.io',
        'url': 'https://api.gateio.ws/api/v4/spot/tickers?currency_pair=TON_USDT',
        'parse': lambda d: (Decimal(d[0]['last']), Decimal(d[0]['change_percentage']))
    },
    {
        'name': 'CoinGecko',
        'url': 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true',
        'parse': lambda d: (Decimal(str(d['the-open-network']['usd'])), Decimal(str(d['the-open-network']['usd_24h_change'])))
    },
]


class TonPriceBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.session = None
        self.prev_price = None
        self.prev_change = None
        self.last_message = None

    async def get_price_from_api(self, api):
        try:
            async with self.session.get(api['url'], timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    price, change = api['parse'](data)
                    return price, change, api['name']
        except:
            pass
        return None, None, None

    async def get_best_price(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        for api in APIS:
            price, change, name = await self.get_price_from_api(api)
            
            if price is None:
                continue
            
            price_str = str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            change_str = f"{change:.2f}"
            
            if self.prev_price is None:
                logger.info(f"✅ {name}: ${price_str} [{change_str}%]")
                return price, change, name
            
            if price != self.prev_price or change != self.prev_change:
                logger.info(f"✅ {name}: ${price_str} [{change_str}%]")
                return price, change, name
            else:
                logger.info(f"⏭️ {name}: تکراری")
        
        return None, None, None

    async def send_price(self):
        price, change, source = await self.get_best_price()
        
        if price is None:
            logger.info("❌ همه API ها تکراری")
            return False
        
        price_str = str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))
        change_str = f"{change:.2f}"
        
        if self.prev_price is None:
            arrow = "▲"
        elif price > self.prev_price or change > self.prev_change:
            arrow = "▲"
        elif price < self.prev_price or change < self.prev_change:
            arrow = "▼"
        else:
            return False
        
        if change > 0:
            change_text = f"[+{change_str}%]"
        else:
            change_text = f"[{change_str}%]"
        
        message = f"<b>${price_str} {arrow} {change_text}</b>"
        
        if message == self.last_message:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"✅ {source}: {message}")
            
            self.prev_price = price
            self.prev_change = change
            self.last_message = message
            return True
        except Exception as e:
            logger.error(f"❌ {e}")
            return False

    async def run(self):
        logger.info("🚀 شروع")
        
        me = await self.bot.get_me()
        logger.info(f"@{me.username}")
        
        await self.send_price()
        
        while True:
            await asyncio.sleep(60)
            await self.send_price()


if __name__ == '__main__':
    bot = TonPriceBot()
    asyncio.run(bot.run())
