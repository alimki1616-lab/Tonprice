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

BOT_TOKEN = '8264511538:AAEYRrFXqyHSOSO0WXGpCblAdNY7mOGuMfQ'
CHANNEL_USERNAME = '@TonPricx'

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
        'parse': lambda d: (Decimal(d['lastPrice']), Decimal(d['priceChangePercent']))
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
        self.last_message = None

    async def wait_for_next_minute(self):
        now = datetime.now(timezone.utc)
        wait_time = 60 - now.second - (now.microsecond / 1000000)
        if wait_time > 0:
            logger.info(f"⏳ انتظار {wait_time:.1f} ثانیه")
            await asyncio.sleep(wait_time)

    async def get_price_from_api(self, api):
        try:
            async with self.session.get(api['url'], timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    price, change = api['parse'](data)
                    return price, change, api['name']
        except Exception as e:
            logger.debug(f"خطا در {api['name']}: {e}")
        return None, None, None

    async def get_best_price(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        for api in APIS:
            price, change, name = await self.get_price_from_api(api)
            if price is not None:
                return price, change, name
        
        return None, None, None

    async def send_price(self):
        price, change, source = await self.get_best_price()
        
        if price is None:
            logger.error("❌ هیچ API پاسخ نداد")
            return False
        
        price_str = str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))
        change_str = f"{change:.2f}"
        
        if self.prev_price is None:
            arrow = "▲" if change >= 0 else "▼"
        else:
            if price > self.prev_price:
                arrow = "▲"
            elif price < self.prev_price:
                arrow = "▼"
            else:
                arrow = "▲" if change >= 0 else "▼"
        
        if change >= 0:
            change_text = f"[+{change_str}%]"
        else:
            change_text = f"[{change_str}%]"
        
        message = f"<b>${price_str} {arrow} {change_text}</b>"
        
        if message == self.last_message:
            logger.info(f"⏭️ پیام تکراری - ارسال نشد: {message}")
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
            self.last_message = message
            return True
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال: {e}")
            return False

    async def run(self):
        logger.info("🚀 شروع بات قیمت TON")
        
        try:
            me = await self.bot.get_me()
            logger.info(f"✅ بات متصل شد: @{me.username}")
        except Exception as e:
            logger.error(f"❌ خطا در اتصال به بات: {e}")
            return
        
        while True:
            await self.wait_for_next_minute()
            await self.send_price()


if __name__ == '__main__':
    bot = TonPriceBot()
    asyncio.run(bot.run())
