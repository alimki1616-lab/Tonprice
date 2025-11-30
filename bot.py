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

# API های صرافی با درصد تغییرات واقعی
BINANCE_24HR_API = 'https://api.binance.com/api/v3/ticker/24hr?symbol=TONUSDT'
COINGECKO_API = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'


class TonPriceBot:
    def __init__(self, token, channel):
        self.bot = Bot(token=token)
        self.channel = channel
        self.session = None
        self.last_sent_price = None
        self.last_sent_change = None
        self.is_first_message = True

    async def get_ton_price_from_exchange(self):
        """دریافت قیمت و درصد تغییرات واقعی از صرافی"""
        
        for attempt in range(3):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()
                
                # اولویت 1: Binance 24hr ticker - درصد 24 ساعته از صرافی
                try:
                    async with self.session.get(BINANCE_24HR_API, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            current_price = Decimal(str(data['lastPrice']))
                            change_percent = Decimal(str(data['priceChangePercent']))
                            
                            logger.info(f"✅ Binance: قیمت=${current_price} | تغییرات 24h={change_percent:.2f}% (از صرافی)")
                            return current_price, change_percent
                except Exception as e:
                    logger.warning(f"Binance خطا: {e}")
                
                # اولویت 2: CoinGecko - درصد 24 ساعته
                try:
                    async with self.session.get(COINGECKO_API, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            if 'the-open-network' in data:
                                ton_data = data['the-open-network']
                                current_price = Decimal(str(ton_data['usd']))
                                change_percent = Decimal(str(ton_data.get('usd_24h_change', 0)))
                                
                                logger.info(f"✅ CoinGecko: قیمت=${current_price} | تغییرات 24h={change_percent:.2f}%")
                                return current_price, change_percent
                except Exception as e:
                    logger.warning(f"CoinGecko خطا: {e}")
                
                if attempt < 2:
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"خطا در تلاش {attempt + 1}: {e}")
        
        logger.error("❌ نتوانستیم از هیچ منبع قیمت دریافت کنیم")
        return None, None

    async def format_message(self, price, change_percent):
        """فرمت پیام - نمایش دقیقاً 3 رقم اعشار با درصد تغییرات و فلش"""
        price_rounded = price.quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        price_str = f"${price_rounded:.3f}"
        
        if change_percent > 0:
            symbol = "▲"
            change_str = f"[+{change_percent:.2f}%]"
        elif change_percent < 0:
            symbol = "▼"
            change_str = f"[{change_percent:.2f}%]"
        else:
            symbol = "▬"
            change_str = f"[{change_percent:.2f}%]"
        
        message = f"<b>{price_str} {symbol} {change_str}</b>"
        return message

    async def send_price_update(self):
        """ارسال قیمت به کانال"""
        try:
            price, change_percent = await self.get_ton_price_from_exchange()
            
            if price is None or change_percent is None:
                logger.error("❌ نتوانستیم قیمت یا درصد تغییرات دریافت کنیم")
                return False
            
            if change_percent == 0:
                logger.info(f"⏭️ تغییر صفر است، ارسال نمی‌شود: ${price} [0.00%]")
                return False
            
            if self.last_sent_price is not None and self.last_sent_change is not None:
                price_diff = abs(price - self.last_sent_price)
                change_diff = abs(change_percent - self.last_sent_change)
                
                if price_diff < Decimal('0.001') and change_diff < Decimal('0.01'):
                    logger.info(f"⏭️ قیمت تکراری است، ارسال نمی‌شود: ${price} [{change_percent:.2f}%]")
                    return False
            
            message = await self.format_message(price, change_percent)
            
            await self.bot.send_message(
                chat_id=self.channel,
                text=message,
                parse_mode=ParseMode.HTML
            )
            
            self.last_sent_price = price
            self.last_sent_change = change_percent
            self.is_first_message = False
            
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            logger.info(f"✅ پیام ارسال شد: {message} - {current_time}")
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
                now = datetime.now(timezone.utc)
                seconds_to_wait = 60 - now.second
                logger.info(f"⏳ صبر {seconds_to_wait} ثانیه تا دقیقه بعدی...")
                await asyncio.sleep(seconds_to_wait)
                
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
