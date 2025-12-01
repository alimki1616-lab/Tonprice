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

COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'


class TonPriceBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.session = None
        self.prev_price = None
        self.prev_change = None
        self.last_message = None

    async def get_price(self):
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(COINGECKO_API, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'the-open-network' in data:
                        ton = data['the-open-network']
                        price = Decimal(str(ton['usd']))
                        change = Decimal(str(ton.get('usd_24h_change', 0)))
                        logger.info(f"CoinGecko: ${price} | {change:.2f}%")
                        return price, change
        except Exception as e:
            logger.error(f"خطا: {e}")
        return None, None

    async def send_price(self):
        price, change = await self.get_price()
        
        if price is None:
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
            self.prev_price = price
            self.prev_change = change
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
            logger.info(f"✅ {message}")
            
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
