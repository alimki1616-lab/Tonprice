import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
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
        'name': 'MEXC',
        'url': 'https://api.mexc.com/api/v3/ticker/24hr?symbol=TONUSDT',
        'parse': lambda d: (Decimal(d['lastPrice']), Decimal(d['priceChangePercent']) * 100)
    },
    {
        'name': 'HTX',
        'url': 'https://api.huobi.pro/market/detail/merged?symbol=tonusdt',
        'parse': lambda d: (Decimal(str(d['tick']['close'])), ((Decimal(str(d['tick']['close'])) - Decimal(str(d['tick']['open']))) / Decimal(str(d['tick']['open']))) * 100)
    },
    {
        'name': 'Bitget',
        'url': 'https://api.bitget.com/api/v2/spot/market/tickers?symbol=TONUSDT',
        'parse': lambda d: (Decimal(d['data'][0]['lastPr']), Decimal(d['data'][0]['change24h']) * 100)
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
        self.prev_price_str = None
        self.prev_change_str = None
        self.last_message = None

    async def wait_for_next_minute(self):
        now = datetime.now(timezone.utc)
        wait_time = 60 - now.second - (now.microsecond / 1000000)
        if wait_time > 0:
            logger.info(f"⏳ {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

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

    async def get_new_price(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        for api in APIS:
            price, change, name = await self.get_price_from_api(api)
            
            if price is None:
                continue
            
            price_str = str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            change_str = f"{change:.2f}"
            
            if self.prev_price_str is None:
                logger.info(f"✅ {name}: ${price_str} [{change_str}%]")
                return price, change, price_str, change_str, name
            
            if price_str != self.prev_price_str or change_str != self.prev_change_str:
                logger.info(f"✅ {name}: ${price_str} [{change_str}%]")
                return price, change, price_str, change_str, name
            else:
                logger.info(f"⏭️ {name}: تکراری")
        
        return None, None, None, None, None

    async def send_price(self):
        result = await self.get_new_price()
        price, change, price_str, change_str, source = result
        
        if price is None:
            logger.info("❌ همه تکراری")
            return False
        
        if self.prev_price is None:
            arrow = "▲"
        elif price > self.prev_price:
            arrow = "▲"
        elif price < self.prev_price:
            arrow = "▼"
        elif change > self.prev_change:
            arrow = "▲"
        elif change < self.prev_change:
            arrow = "▼"
        else:
            arrow = "▲"
        
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
            now = datetime.now(timezone.utc).strftime('%H:%M:%S')
            logger.info(f"✅ [{now}] {source}: {message}")
            
            self.prev_price = price
            self.prev_change = change
            self.prev_price_str = price_str
            self.prev_change_str = change_str
            self.last_message = message
            return True
        except Exception as e:
            logger.error(f"❌ {e}")
            return False

    async def run(self):
        logger.info("🚀 شروع")
        
        me = await self.bot.get_me()
        logger.info(f"@{me.username}")
        
        while True:
            await self.wait_for_next_minute()
            await self.send_price()


if __name__ == '__main__':
    bot = TonPriceBot()
    asyncio.run(bot.run())
