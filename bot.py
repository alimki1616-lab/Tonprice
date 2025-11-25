import os
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
import aiohttp

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تنظیمات از محیط
BOT_TOKEN = os.getenv('BOT_TOKEN', '8319365970:AAE9vdXVQ11arGG7DK_3N11VfdBkBO1FeFQ')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@tonpricepro')

# API برای دریافت قیمت Toncoin با دقت بالا
KUCOIN_API = 'https://api.kucoin.com/api/v1/market/orderbook/level1?symbol=TON-USDT'
OKX_API = 'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT'
BINANCE_API = 'https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT'
COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.last_price = None

    async def get_ton_price(self):
        """دریافت قیمت Toncoin با retry و دقت بالا"""
        # تلاش 3 بار
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: KuCoin (4 رقم اعشار)
                try:
                    async with self.session.get(KUCOIN_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '200000' and 'data' in data:
                                price = Decimal(str(data['data']['price']))
                                logger.info(f"✅ قیمت از KuCoin: ${price}")
                                self.last_price = price
                                return price
                except Exception as e:
                    logger.warning(f"KuCoin خطا: {e}")
                
                # اولویت 2: OKX (3 رقم اعشار)
                try:
                    async with self.session.get(OKX_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '0' and 'data' in data:
                                price = Decimal(str(data['data'][0]['last']))
                                logger.info(f"✅ قیمت از OKX: ${price}")
                                self.last_price = price
                                return price
                except Exception as e:
                    logger.warning(f"OKX خطا: {e}")
                
                # اولویت 3: Binance (پشتیبان)
                try:
                    async with self.session.get(BINANCE_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            price = Decimal(str(data['price']))
                            logger.info(f"✅ قیمت از Binance: ${price}")
                            self.last_price = price
                            return price
                except Exception as e:
                    logger.warning(f"Binance خطا: {e}")
                
                # اولویت 4: CoinGecko (پشتیبان)
                try:
                    async with self.session.get(COINGECKO_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            price = Decimal(str(data['the-open-network']['usd']))
                            logger.info(f"✅ قیمت از CoinGecko: ${price}")
                            self.last_price = price
                            return price
                except Exception as e:
                    logger.warning(f"CoinGecko خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        # اگر همه تلاش‌ها ناموفق بود، از قیمت قبلی استفاده کن
        if self.last_price:
            logger.warning(f"⚠️ استفاده از قیمت قبلی: ${self.last_price}")
            return self.last_price
        
        return None

    async def format_message(self, price):
        """فرمت پیام به صورت بولد - نمایش دقیقاً 3 رقم اعشار"""
        price_rounded = price.quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        price_str = f"{price_rounded:.3f}"
        message = f"<b>{price_str} $</b>"
        return message

    async def send_price_update(self):
        """ارسال قیمت به کانال"""
        try:
            price = await self.get_ton_price()
            
            if price is None:
                logger.error("❌ نتوانستیم قیمت دریافت کنیم")
                return False
            
            message = await self.format_message(price)
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"✅ قیمت ارسال شد: {message} - {current_time}")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ خطای تلگرام: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ خطای غیرمنتظره: {e}")
            return False

    async def run(self):
        """اجرای ربات"""
        logger.info("🚀 ربات شروع شد")
        logger.info(f"📢 کانال: {self.channel}")
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"✅ ربات متصل: @{bot_info.username}")
            
            while True:
                # صبر تا شروع دقیقه بعدی
                now = datetime.now(timezone.utc)
                seconds_to_wait = 60 - now.second
                logger.info(f"⏳ صبر {seconds_to_wait} ثانیه تا دقیقه بعدی...")
                await asyncio.sleep(seconds_to_wait)
                
                # ارسال قیمت
                await self.send_price_update()
                
        except KeyboardInterrupt:
            logger.info("⛔ ربات متوقف شد")
        except Exception as e:
            logger.error(f"❌ خطای کلی: {e}")
            await asyncio.sleep(60)
        finally:
            if self.session:
                await self.session.close()


async def main():
    """تابع اصلی"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN تنظیم نشده!")
        return
    
    bot = TonPriceBot(BOT_TOKEN, CHANNEL_USERNAME)
    await bot.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ برنامه متوقف شد")
