/* ============================================================
   FinanceIQ — funfacts.js
   A new market/finance fun fact every day, shown on every page.
   Selection is deterministic (based on the date) so everyone sees
   the same fact on a given day, and it changes automatically at
   midnight local time.
   ============================================================ */

const MARKET_FUN_FACTS = [
  "The Bombay Stock Exchange (BSE), founded in 1875, is Asia's oldest stock exchange.",
  "The NSE's Nifty 50 index was launched in 1996 and tracks 50 of India's largest listed companies.",
  "India's stock markets are open Monday to Friday, 9:15 AM to 3:30 PM IST, with a pre-open session from 9:00–9:15 AM.",
  "SEBI (Securities and Exchange Board of India) was established in 1988 and given statutory powers in 1992 to regulate the securities market.",
  "A 'circuit breaker' temporarily halts trading on Indian exchanges if the Nifty or Sensex moves more than 10%, 15%, or 20% in a day.",
  "The term 'Sensex' is a blend of 'Sensitive' and 'Index' — it tracks 30 of the largest and most actively traded stocks on the BSE.",
  "India became the world's most populous country in 2023, a factor many investors cite as a long-term growth driver for its markets.",
  "T+1 settlement means shares you buy are typically credited to your demat account just one working day after the trade.",
  "Mutual fund SIPs (Systematic Investment Plans) let you invest a fixed amount regularly, helping average out purchase costs over time — known as rupee-cost averaging.",
  "The Reserve Bank of India (RBI) was established in 1935 and is the country's central bank, setting policy rates like the repo rate.",
  "A 'bull market' refers to rising prices and investor optimism, while a 'bear market' refers to falling prices and pessimism — named after how each animal attacks.",
  "Gold has historically been seen as a hedge against inflation and currency depreciation, which is why many Indian households hold it as an investment.",
  "The P/E (Price-to-Earnings) ratio compares a company's share price to its earnings per share — a higher P/E can signal high growth expectations.",
  "India's GDP is the among the fastest-growing of any major economy, with services contributing over half of total output.",
  "The 'IPO' process lets a private company sell shares to the public for the first time, often to raise funds for expansion.",
  "Diversification — spreading investments across sectors and asset classes — is one of the simplest ways to reduce portfolio risk.",
  "The Nifty Bank index tracks the most liquid and large banking stocks listed on the NSE, often seen as a barometer for the financial sector.",
  "Dividend yield is the annual dividend per share divided by the share price — it shows how much income an investment generates relative to its cost.",
  "FII stands for Foreign Institutional Investors — their buying or selling activity can significantly move Indian markets in either direction.",
  "Compounding means earning returns not just on your original investment, but also on the returns it has already generated — Einstein reportedly called it one of the most powerful forces.",
  "India's CPI (Consumer Price Index) inflation target set by the RBI is 4%, with a tolerance band of +/- 2%.",
  "A 'stock split' increases the number of shares outstanding while proportionally reducing the price — it doesn't change a company's total market value.",
  "The Nifty Midcap and Smallcap indices track mid-sized and smaller companies, which can offer higher growth potential but often come with higher volatility.",
  "Index funds aim to replicate a market index like the Nifty 50 rather than trying to beat it, usually at a much lower cost than actively managed funds.",
  "Demat (dematerialized) accounts, introduced in India in 1996, let investors hold shares electronically instead of as physical certificates.",
  "The 'PE ratio' of the Nifty 50 is often used as a quick gauge of whether the broader market looks expensive or cheap relative to history.",
  "Section 80C of the Income Tax Act allows deductions up to ₹1.5 lakh per year for investments like ELSS mutual funds, PPF, and life insurance premiums.",
  "Market capitalization is calculated by multiplying a company's share price by its total number of outstanding shares.",
  "India's first mutual fund, the Unit Trust of India (UTI), was established in 1963.",
  "A 'blue-chip' stock refers to shares of large, financially stable, and well-established companies with a history of reliable performance.",
  "The repo rate is the rate at which the RBI lends short-term funds to commercial banks — changes in it ripple through loan and deposit rates across the economy.",
  "Gold ETFs let investors gain exposure to gold prices without needing to store physical gold, and trade just like stocks on an exchange.",
  "The term 'arbitrage' refers to profiting from price differences of the same asset across different markets or forms.",
  "India's Goods and Services Tax (GST), introduced in 2017, replaced multiple indirect taxes with a single unified tax structure.",
  "A company's 'book value' is its total assets minus total liabilities — sometimes used to assess whether a stock is undervalued relative to its assets.",
  "The Nifty 50 was first introduced with a base value of 1000 on November 3, 1995 (base date), and has grown more than 20x since.",
  "ESG investing considers Environmental, Social, and Governance factors alongside financial returns when evaluating companies.",
  "India's foreign exchange reserves are among the largest in the world, acting as a buffer against external economic shocks.",
  "A 'rights issue' allows existing shareholders to buy additional shares, usually at a discount, in proportion to their current holding.",
  "The term 'rupee cost averaging' describes how regular fixed investments buy more units when prices are low and fewer when prices are high, smoothing out volatility over time.",
];

function getDailyFunFact() {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 0);
  const diff = now - start;
  const dayOfYear = Math.floor(diff / (1000 * 60 * 60 * 24));
  return MARKET_FUN_FACTS[dayOfYear % MARKET_FUN_FACTS.length];
}

function loadDailyFunFact() {
  const el = document.getElementById("funFactText");
  if (!el) return;
  el.textContent = getDailyFunFact();
}
