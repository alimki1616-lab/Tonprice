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
BOT_TOKEN = os.getenv('BOT_TOKEN', '8326225213:AAGsScRkwKKGipb_z_57vfGeDBw6Iz-hkdA')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@Ton24Price')

# API صرافی
BINANCE_24HR_API = 'https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT'
COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        # برای بررسی تکراری بودن
        self.last_sent_price_str = None
        self.last_sent_change_str = None
        # برای محاسبه فلش (مقایسه با دقیقه قبل)
        self.previous_price = None

    async def get_ton_price_from_exchange(self):
        """دریافت قیمت و درصد 24 ساعته از صرافی"""
        
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: Binance
                try:
                    async with self.session.get(BINANCE_24HR_API, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            data = await response.json()
                            current_price = Decimal(str(data['lastPrice']))
                            change_24h = Decimal(str(data['priceChangePercent']))
                            
                            logger.info(f"✅ Binance: ${current_price} | 24h: {change_24h:.2f}%")
                            return current_price, change_24h
                except Exception as e:
                    logger.warning(f"Binance خطا: {e}")
                
                # اولویت 2: CoinGecko
                try:
                    async with self.session.get(COINGECKO_API, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            data = await response.json()
                            if 'the-open-network' in data:
                                ton_data = data['the-open-network']
                                current_price = Decimal(str(ton_data['usd']))
                                change_24h = Decimal(str(ton_data.get('usd_24h_change', 0)))
                                
                                logger.info(f"✅ CoinGecko: ${current_price} | 24h: {change_24h:.2f}%")
                                return current_price, change_24h
                except Exception as e:
                    logger.warning(f"CoinGecko خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        logger.error("❌ دریافت قیمت ناموفق")
        return None, None

    def format_price_str(self, price):
        """گرد کردن قیمت به 3 رقم اعشار"""
        return str(price.quantize(Decimal('0.001'), rounding=ROUND_DOWN))

    def format_change_str(self, change):
        """گرد کردن درصد به 2 رقم اعشار"""
        return f"{change:.2f}"

    def get_arrow(self, current_price):
        """فلش بر اساس مقایسه با قیمت دقیقه قبل"""
        if self.previous_price is None:
            return "▬"  # اولین پیام
        
        if current_price > self.previous_price:
            return "▲"  # قیمت بالا رفت
        elif current_price < self.previous_price:
            return "▼"  # قیمت پایین آمد
        else:
            return "▬"  # بدون تغییر

    def is_duplicate(self, price_str, change_str):
        """بررسی تکراری بودن - مقایسه رشته‌ای دقیق"""
        if self.last_sent_price_str is None:
            return False
        
        return price_str == self.last_sent_price_str and change_str == self.last_sent_change_str

    def format_message(self, price_str, change_24h, arrow):
        """ساخت پیام نهایی"""
        change_val = Decimal(change_24h)
        
        if change_val > 0:
            change_text = f"[+{change_24h}%]"
        else:
            change_text = f"[{change_24h}%]"
        
        return f"<b>${price_str} {arrow} {change_text}</b>"

    async def send_price_update(self):
        """ارسال قیمت به کانال"""
        try:
            price, change_24h = await self.get_ton_price_from_exchange()
            
            if price is None or change_24h is None:
                logger.error("❌ دریافت قیمت ناموفق")
                return False
            
            # فرمت کردن مقادیر
            price_str = self.format_price_str(price)
            change_str = self.format_change_str(change_24h)
            
            # بررسی تکراری بودن
            if self.is_duplicate(price_str, change_str):
                logger.info(f"⏭️ تکراری: ${price_str} [{change_str}%]")
                # قیمت قبلی را آپدیت نمی‌کنیم چون ارسال نشد
                return False
            
            # فلش بر اساس مقایسه با دقیقه قبل
            arrow = self.get_arrow(price)
            
            # ساخت پیام
            message = self.format_message(price_str, change_str, arrow)
            
            # ارسال به کانال
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            # ذخیره برای بررسی تکراری
            self.last_sent_price_str = price_str
            self.last_sent_change_str = change_str
            
            # ذخیره برای محاسبه فلش دقیقه بعد
            self.previous_price = price
            
            logger.info(f"✅ ارسال: {message}")
            return True
            
        except TelegramError as e:
            logger.error(f"❌ خطای تلگرام: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ خطا: {e}")
            return False

    async def run(self):
        """اجرای ربات - هر 60 ثانیه دقیق"""
        logger.info("🚀 ربات شروع شد")
        logger.info(f"📢 کانال: {self.channel}")
        
        try:
            bot_info = await self.bot.get_me()
            logger.info(f"✅ متصل: @{bot_info.username}")
            
            # اولین ارسال فوری
            await self.send_price_update()
            
            while True:
                # صبر دقیقاً 60 ثانیه
                await asyncio.sleep(60)
                await self.send_price_update()
                
        except KeyboardInterrupt:
            logger.info("⛔ متوقف شد")
        except Exception as e:
            logger.error(f"❌ خطا: {e}")
        finally:
            if self.session:
                await self.session.close()


async def main():
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
