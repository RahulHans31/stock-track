import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

// Your fixed pincodes
const PINCODES_TO_CHECK = ['132001', '110016'];

// --- TELEGRAM HELPER ---
async function sendTelegramMessage(message) {
  const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
  const CHAT_ID = process.env.TELEGRAM_CHAT_ID;
  if (!BOT_TOKEN || !CHAT_ID) {
    console.warn('Telegram env variables not set. Skipping message.');
    return;
  }
  const url = `https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`;
  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: CHAT_ID, text: message, parse_mode: 'Markdown', disable_web_page_preview: true
    }),
  });
}

// --- CROMA CHECKER ---
async function checkCroma(product, pincode) {
  const url = 'https.api.croma.com/inventory/oms/v2/tms/details-pwa/';
  const payload = { promise: { allocationRuleID: 'SYSTEM', checkInventory: 'Y', organizationCode: 'CROMA', sourcingClassification: 'EC', promiseLines: { promiseLine: [{ fulfillmentType: 'HDEL', itemID: product.productId, lineId: '1', requiredQty: '1', shipToAddress: { zipCode: pincode, extn: {} }, extn: { widerStoreFlag: 'N' } }] } } };
  const headers = { 'accept': 'application/json', 'content-type': 'application/json', 'oms-apim-subscription-key': '1131858141634e2abe2efb2b3a2a2a5d', 'origin': 'https.www.croma.com', 'referer': 'https.www.croma.com/' };
  try {
    const res = await fetch(url, { method: 'POST', headers: headers, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(`Croma API error: ${res.status}`);
    const data = await res.json();

    // --- DEBUGGING LINE ---
    console.log(`CROMA_DEBUG (${product.name}): ${JSON.stringify(data)}`);
    // ------------------------

    if (data.promise?.suggestedOption?.option?.promiseLines?.promiseLine?.length > 0) {
      return `✅ *In Stock at Croma (${pincode})*\n[${product.name}](${product.url})`;
    }
  } catch (error) { console.error(`Error checking Croma (${product.name}): ${error.message}`); }
  return null;
}

// --- FLIPKART CHECKER ---
async function checkFlipkart(product, pincode) {
  const url = 'https.2.rome.api.flipkart.com/api/3/product/serviceability';
  const payload = { requestContext: { products: [{ productId: product.productId }] }, locationContext: { pincode: pincode } };
  
  // These headers now include the MRA58N User-Agent fix
  const headers = { 
    "Accept": "application/json", 
    "Content-Type": "application/json", 
    "Origin": "https.www.flipkart.com", 
    "Referer": "https.www.flipkart.com/", 
    // --- THIS LINE IS NOW FIXED ---
    "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    // ----------------------------
    "X-User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36 FKUA/msite/0.0.3/msite/Mobile" 
  };
  
  try {
    const res = await fetch(url, { method: 'POST', headers: headers, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(`Flipkart API error: ${res.status}`);
    const data = await res.json();

    // --- DEBUGGING LINE ---
    console.log(`FLIPKART_DEBUG (${product.name}): ${JSON.stringify(data)}`);
    // ------------------------

    const listing = data.RESPONSE?.[product.productId]?.listingSummary;
    if (listing?.serviceable === true && listing?.available === true) {
      return `✅ *In Stock at Flipkart (${pincode})*\n[${product.name}](${product.url})`;
    }
  } catch (error) { console.error(`Error checking Flipkart (${product.name}): ${error.message}`); }
  return null;
}

// --- MAIN SCRIPT EXECUTION ---
async function runChecks() {
  console.log('Starting stock check...');
  
  let productsToTrack;
  try {
    productsToTrack = await prisma.product.findMany();
    console.log(`Found ${productsToTrack.length} products in the database.`);
  } catch (error) {
    console.error('Failed to fetch products from database:', error);
    await sendTelegramMessage(`❌ Your checker script failed to connect to the database.`);
    return;
  }

  const allChecks = [];
  for (const product of productsToTrack) {
    for (const pincode of PINCODES_TO_CHECK) {
      if (product.storeType === 'croma') allChecks.push(checkCroma(product, pincode));
      else if (product.storeType === 'flipkart') allChecks.push(checkFlipkart(product, pincode));
    }
  }
  const results = await Promise.allSettled(allChecks);
  const inStockMessages = results
    .filter(res => res.status === 'fulfilled' && res.value !== null)
    .map(res => res.value);

  if (inStockMessages.length > 0) {
    console.log(`Found ${inStockMessages.length} items in stock. Sending Telegram message.`);
    const finalMessage = "🔥 *Stock Alert!*\n\n" + inStockMessages.join('\n\n');
    await sendTelegramMessage(finalMessage);
  } else {
    console.log('All items out of stock. No message sent.');
  }
}

// Run the script and disconnect Prisma
runChecks()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });