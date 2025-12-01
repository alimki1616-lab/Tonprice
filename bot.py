import os
import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
import aiohttp

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '8326225213:AAGsScRkwKKGipb_z_57vfGeDBw6Iz-hkdA')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@Ton24Price')

BINANCE_API = 'https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.prev_price = None
        self.prev_change = None
        self.last_message = None

    async def get_price(self):
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(BINANCE_API, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    price = Decimal(str(data['lastPrice']))
                    change = Decimal(str(data['priceChangePercent']))
                    return price, change
        except Exception as e:
            logger.error(f"خطا: {e}")
        return None, None

    async def send_price(self):
        try:
            price, change = await self.get_price()
            
            if price is None:
                return False
            
            price_str = str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))
            change_str = f"{change:.2f}"
            
            if self.prev_price is None:
                self.prev_price = price
                self.prev_change = change
                logger.info(f"📌 اولیه: ${price_str} [{change_str}%]")
                return False
            
            price_up = price > self.prev_price
            price_down = price < self.prev_price
            change_up = change > self.prev_change
            change_down = change < self.prev_change
            
            if price_up or change_up:
                arrow = "▲"
            elif price_down or change_down:
                arrow = "▼"
            else:
                logger.info(f"⏭️ بدون تغییر: ${price_str}")
                return False
            
            if change > 0:
                change_text = f"[+{change_str}%]"
            else:
                change_text = f"[{change_str}%]"
            
            message = f"<b>${price_str} {arrow} {change_text}</b>"
            
            if message == self.last_message:
                logger.info(f"⏭️ تکراری")
                return False
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            self.prev_price = price
            self.prev_change = change
            self.last_message = message
            logger.info(f"✅ {message}")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ {e}")
            return False

    async def run(self):
        logger.info("🚀 شروع")
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"✅ @{bot_info.username}")
            
            await self.send_price()
            
            while True:
                await asyncio.sleep(60)
                await self.send_price()
                
        except Exception as e:
            logger.error(f"❌ {e}")
        finally:
            if self.session:
                await self.session.close()


async def main():
    bot = TonPriceBot(BOT_TOKEN, CHANNEL_USERNAME)
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())
