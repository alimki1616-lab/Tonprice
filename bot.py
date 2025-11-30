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

# API برای دریافت قیمت Toncoin با دقت بالا
BINANCE_TICKER_API = 'https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT'
BINANCE_KLINE_API = 'https://api.binance.com/api/v3/klines?symbol=TONUSDT&interval=1m&limit=2'
OKX_API = 'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT'
KUCOIN_API = 'https://api.kucoin.com/api/v1/market/stats?symbol=TON-USDT'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.last_price = None
        self.last_change_percent = None
        self.last_message = None
        self.previous_price = None  # قیمت دقیقه قبل برای محاسبه تغییرات یک دقیقه‌ای
        self.last_sent_price = None  # آخرین قیمتی که ارسال شده
        self.last_sent_change = None  # آخرین درصد تغییری که ارسال شده

    async def get_ton_price_and_change(self):
        """دریافت قیمت Toncoin و درصد تغییرات یک دقیقه از صرافی"""
        # تلاش 3 بار
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: Binance Klines (کندل 1 دقیقه‌ای)
                try:
                    async with self.session.get(BINANCE_KLINE_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if len(data) >= 2:
                                # کندل دوم از آخر (دقیقه قبل - بسته شده)
                                prev_candle = data[-2]
                                prev_close = Decimal(str(prev_candle[4]))  # قیمت بسته شدن دقیقه قبل
                                
                                # کندل آخر (دقیقه فعلی - در حال تشکیل)
                                current_candle = data[-1]
                                current_price = Decimal(str(current_candle[4]))  # قیمت فعلی
                                
                                # محاسبه درصد تغییرات یک دقیقه
                                one_min_change = ((current_price - prev_close) / prev_close) * 100
                                
                                logger.info(f"✅ قیمت از Binance: ${current_price} | تغییرات 1 دقیقه: {one_min_change:.2f}%")
                                self.last_price = current_price
                                self.last_change_percent = one_min_change
                                return current_price, one_min_change
                except Exception as e:
                    logger.warning(f"Binance Klines خطا: {e}")
                
                # اولویت 2: OKX (استفاده از قیمت باز و فعلی)
                try:
                    async with self.session.get(OKX_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '0' and 'data' in data:
                                ticker = data['data'][0]
                                current_price = Decimal(str(ticker['last']))
                                open_price = Decimal(str(ticker['open24h']))  # قیمت باز 24 ساعته (بهترین گزینه موجود)
                                
                                # اگر قیمت قبلی داریم، از آن استفاده کنیم
                                if self.last_price:
                                    one_min_change = ((current_price - self.last_price) / self.last_price) * 100
                                else:
                                    one_min_change = Decimal('0')
                                
                                logger.info(f"✅ قیمت از OKX: ${current_price} | تغییرات 1 دقیقه: {one_min_change:.2f}%")
                                self.last_price = current_price
                                self.last_change_percent = one_min_change
                                return current_price, one_min_change
                except Exception as e:
                    logger.warning(f"OKX خطا: {e}")
                
                # اولویت 3: KuCoin
                try:
                    async with self.session.get(KUCOIN_API, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('code') == '200000' and 'data' in data:
                                stats = data['data']
                                current_price = Decimal(str(stats['last']))
                                
                                # اگر قیمت قبلی داریم، از آن استفاده کنیم
                                if self.last_price:
                                    one_min_change = ((current_price - self.last_price) / self.last_price) * 100
                                else:
                                    one_min_change = Decimal('0')
                                
                                logger.info(f"✅ قیمت از KuCoin: ${current_price} | تغییرات 1 دقیقه: {one_min_change:.2f}%")
                                self.last_price = current_price
                                self.last_change_percent = one_min_change
                                return current_price, one_min_change
                except Exception as e:
                    logger.warning(f"KuCoin خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        # اگر همه تلاش‌ها ناموفق بود، از داده قبلی استفاده کن
        if self.last_price and self.last_change_percent is not None:
            logger.warning(f"⚠️ استفاده از داده قبلی: ${self.last_price} | {self.last_change_percent}%")
            return self.last_price, self.last_change_percent
        
        return None, None

    async def format_message(self, price, change_percent):
        """فرمت پیام - نمایش دقیقاً 3 رقم اعشار با درصد تغییرات و نماد"""
        # قیمت با 3 رقم اعشار
        price_rounded = price.quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        price_str = f"${price_rounded:.3f}"
        
        # تعیین نماد بر اساس مثبت یا منفی بودن
        if change_percent > 0:
            symbol = "🟢"
            change_str = f"[+{change_percent:.2f}%]"
        elif change_percent < 0:
            symbol = "🔴"
            change_str = f"[{change_percent:.2f}%]"
        else:
            symbol = "⚪"
            change_str = f"[{change_percent:.2f}%]"
        
        # فرمت نهایی: $1.578 🟢 [+3.44%]
        message = f"<b>{price_str} {symbol} {change_str}</b>"
        return message

    async def send_price_update(self):
        """ارسال قیمت به کانال - با درصد تغییرات یک دقیقه از صرافی"""
        try:
            price, one_min_change = await self.get_ton_price_and_change()
            
            if price is None or one_min_change is None:
                logger.error("❌ نتوانستیم قیمت یا درصد تغییرات دریافت کنیم")
                return False
            
            # جلوگیری از ارسال تکراری: چک کردن قیمت و درصد
            if self.last_sent_price is not None and self.last_sent_change is not None:
                # اگر هم قیمت و هم درصد تغییر نکرده باشد، ارسال نکن
                if price == self.last_sent_price and one_min_change == self.last_sent_change:
                    logger.info(f"⏭️ قیمت و درصد تغییر نکرده، ارسال نمی‌شود: ${price} [{one_min_change:.2f}%]")
                    return False
            
            message = await self.format_message(price, one_min_change)
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            # ذخیره قیمت و درصد ارسال شده
            self.last_sent_price = price
            self.last_sent_change = one_min_change
            
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
