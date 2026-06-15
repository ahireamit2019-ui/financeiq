/* ============================================================
   FinanceIQ — sectionfacts.js
   A new fun fact every day for each major section of the app,
   in addition to the global fun fact bar (funfacts.js).
   Selection is deterministic (based on the date) so everyone sees
   the same fact on a given day, and it changes automatically at
   midnight local time.
   ============================================================ */

const SECTION_FUN_FACTS = {
  // Dashboard
  dashboard: [
    "India is home to over 5,000 companies listed across the NSE and BSE combined.",
    "The Nifty 50 represents roughly two-thirds of the total market capitalisation of NSE-listed companies.",
    "India's stock market trading hours (9:15 AM - 3:30 PM IST) make it one of the shorter trading days among major global exchanges.",
    "Retail investor participation in Indian equities has grown sharply since 2020, with demat account numbers crossing 150 million.",
    "A 'demat account' (dematerialized account) holds your shares electronically, replacing the old system of physical share certificates.",
    "India's market regulator SEBI requires listed companies to disclose financial results every quarter, giving investors regular updates.",
    "The Sensex and Nifty often move in tandem since they share many of the same large constituent stocks.",
    "Indian markets are closed on national holidays and a handful of festival days each year, published in advance by the exchanges.",
    "A 'circuit filter' on individual stocks (commonly 5%, 10%, or 20%) limits how much a share price can move in a single day.",
    "Pre-market session (9:00-9:08 AM) helps determine the opening price based on early buy/sell orders before regular trading begins.",
  ],

  // Stock Search / Stock Research
  stock: [
    "EPS (Earnings Per Share) is a company's net profit divided by its number of outstanding shares - a key measure of profitability per shareholder.",
    "A stock's '52-week high/low' shows the highest and lowest price it has traded at over the past year, often used to gauge momentum.",
    "Promoter holding refers to the percentage of a company's shares owned by its founders or controlling group - high promoter pledging can be a red flag.",
    "ROE (Return on Equity) measures how efficiently a company generates profit from shareholders' money.",
    "A 'bonus issue' gives existing shareholders additional free shares in proportion to their holding, without changing the company's overall value.",
    "Stock splits divide each existing share into multiple shares, lowering the price per share while keeping total investment value the same.",
    "The 'beta' of a stock measures how volatile it is compared to the overall market - a beta above 1 means it tends to move more than the market.",
    "Quarterly results season in India typically runs in the weeks following each financial quarter-end (April, July, October, January).",
    "A company's 'market cap' classification - large, mid, or small cap - is based on its rank by free-float market value among all listed firms.",
    "Insider trading - buying or selling shares based on non-public information - is illegal and closely monitored by SEBI.",
  ],

  // Stock Market
  market: [
    "The Nifty Bank index is often more volatile than the Nifty 50 since banking stocks are highly sensitive to interest rate changes.",
    "FIIs (Foreign Institutional Investors) and DIIs (Domestic Institutional Investors) publish their daily buy/sell activity, closely watched as a sentiment indicator.",
    "A 'sector rotation' happens when investors shift money from one industry group to another based on changing economic expectations.",
    "The India VIX index measures expected market volatility over the next 30 days - often called the market's 'fear gauge'.",
    "Global cues like US Fed rate decisions and crude oil prices often influence the opening direction of Indian markets.",
    "The NSE and BSE both operate T+1 settlement, meaning trades settle the next working day after execution.",
    "'Most active stocks by volume' often reflects where short-term traders are focused, not necessarily where long-term value lies.",
    "Index reshuffles (when stocks are added to or removed from Nifty 50) happen periodically and can cause large fund flows around the change date.",
    "Midcap and smallcap indices tend to be more volatile than large-cap indices but have historically delivered higher long-term returns with higher risk.",
    "A 'gap up' or 'gap down' opening occurs when a stock or index opens significantly above or below its previous closing price, often due to overnight news.",
  ],

  // Mutual Funds
  mutualfunds: [
    "A mutual fund's NAV (Net Asset Value) represents the per-unit value of the fund's holdings, updated once daily after market close.",
    "'Direct plans' of mutual funds have lower expense ratios than 'regular plans' since they cut out distributor commissions.",
    "SIP (Systematic Investment Plan) returns depend heavily on market timing of individual instalments, which is why long-term SIPs tend to smooth out volatility.",
    "An 'expense ratio' is the annual fee a mutual fund charges as a percentage of your investment - even small differences compound significantly over decades.",
    "ELSS (Equity Linked Savings Scheme) funds offer tax deductions under Section 80C but come with a mandatory 3-year lock-in period.",
    "'Exit load' is a fee charged if you redeem mutual fund units before a specified holding period, designed to discourage short-term trading.",
    "A fund's 'AUM' (Assets Under Management) reflects the total market value of investments it manages on behalf of all investors.",
    "Index funds aim to replicate a benchmark like the Nifty 50 exactly, typically charging much lower fees than actively managed funds.",
    "'CAGR' (Compound Annual Growth Rate) smooths out a fund's year-to-year ups and downs into a single average annual return figure.",
    "AMFI (Association of Mutual Funds in India) publishes daily NAVs for all registered mutual fund schemes in the country.",
  ],

  // Macro Economy
  macro: [
    "India's GDP is measured both at 'constant prices' (adjusted for inflation) and 'current prices' (nominal) - growth rate headlines usually refer to constant prices.",
    "The IIP (Index of Industrial Production) tracks output across mining, manufacturing, and electricity, released monthly with a roughly 6-week lag.",
    "PMI (Purchasing Managers' Index) readings above 50 indicate expansion in manufacturing or services activity, while below 50 indicates contraction.",
    "India's fiscal year runs from April 1 to March 31, different from the calendar year used by many other countries.",
    "The Union Budget, typically presented on February 1, sets the government's spending and revenue plans for the upcoming fiscal year.",
    "India's current account deficit (CAD) measures the gap between what the country earns from exports versus what it spends on imports and other payments.",
    "The RBI's Monetary Policy Committee (MPC) meets roughly every two months to decide on the repo rate and overall policy stance.",
    "'Core inflation' excludes volatile food and fuel prices, giving policymakers a clearer view of underlying price trends.",
    "India's services sector contributes more than half of GDP, with IT, financial services, and trade among the largest components.",
    "Foreign Direct Investment (FDI) inflows are tracked as a sign of long-term confidence in India's economy, distinct from more short-term portfolio flows.",
  ],

  // Inflation Tracker
  inflation: [
    "India's CPI (Consumer Price Index) inflation target is 4%, with the RBI mandated to keep it within a 2-6% band.",
    "The CPI basket assigns the largest weight to food and beverages, which is why food prices heavily influence India's headline inflation number.",
    "WPI (Wholesale Price Index) measures price changes at the wholesale/producer level, while CPI measures what consumers actually pay - they can diverge significantly.",
    "'Core CPI' strips out food and fuel, which are often volatile due to seasonal and global supply factors rather than demand trends.",
    "When inflation rises faster than savings account interest rates, the 'real' (inflation-adjusted) return on those savings can turn negative.",
    "The RBI's repo rate is one of its main tools to control inflation - raising rates makes borrowing costlier, which can cool demand and prices.",
    "Rural and urban inflation in India are tracked separately, and can move quite differently depending on monsoon outcomes and local price pressures.",
    "Crude oil price changes feed into Indian inflation both directly (fuel prices) and indirectly (transport costs for almost everything else).",
    "Inflation erodes the purchasing power of cash over time - ₹100 worth of goods today will cost more in rupee terms a year from now if prices rise.",
    "Government schemes that adjust payouts for inflation (like certain pension or wage schemes) are said to be 'inflation-indexed'.",
  ],

  // Tax Updates
  tax: [
    "India's new tax regime (introduced from FY 2020-21) offers lower slab rates but removes most deductions and exemptions available under the old regime.",
    "Section 80C allows deductions of up to ₹1.5 lakh per year for investments like ELSS, PPF, life insurance premiums, and EPF contributions - but only under the old regime.",
    "Long-term capital gains (LTCG) on equity shares held for more than one year are taxed differently from short-term gains (STCG) on shares held for less than a year.",
    "GST (Goods and Services Tax) replaced over a dozen separate central and state indirect taxes when it was introduced in July 2017.",
    "The income tax return (ITR) filing deadline for most individual taxpayers in India typically falls on July 31 each year, though it has occasionally been extended.",
    "TDS (Tax Deducted at Source) means tax is deducted by the payer (like an employer or bank) before you receive the income, and can be claimed back if you've overpaid.",
    "An 'advance tax' obligation applies if your total tax liability for the year exceeds ₹10,000, payable in instalments through the year rather than as a lump sum.",
    "The standard deduction is a flat amount subtracted from salary income before tax is calculated, available under both old and new tax regimes (at different amounts).",
    "Form 26AS and the Annual Information Statement (AIS) show the tax department's record of TDS, TCS, and other financial transactions linked to your PAN.",
    "Senior citizens (60+) and super senior citizens (80+) get higher basic exemption limits and additional deduction benefits under the old tax regime.",
  ],

  // Business & Earnings
  business: [
    "'YoY' (year-on-year) and 'QoQ' (quarter-on-quarter) are the two most common ways companies compare their latest results to prior periods.",
    "An 'earnings call' is a scheduled conference where company management discusses quarterly results and answers questions from analysts and investors.",
    "'Guidance' refers to a company's own forecast for future revenue or profit - markets often react more to whether guidance beats or misses expectations than to the headline numbers themselves.",
    "Operating margin (operating profit divided by revenue) shows how efficiently a company runs its core business, before interest and tax.",
    "A 'merger' combines two companies into one, while an 'acquisition' is when one company buys and absorbs another - both can significantly move stock prices.",
    "Index providers periodically rebalance which companies are included in benchmarks like the Nifty 50, based on rules around market cap and liquidity.",
    "An IPO's 'price band' is the range within which investors can bid for shares before the final issue price is determined based on demand.",
    "'EBITDA' (Earnings Before Interest, Taxes, Depreciation, and Amortization) is often used to compare profitability across companies with different capital structures.",
    "A company 'buying back' its own shares reduces the number of shares outstanding, which can boost earnings per share even if total profit stays flat.",
    "Credit rating agencies assign ratings to a company's debt, reflecting the perceived risk of default - a downgrade can raise a company's future borrowing costs.",
  ],

  // Geopolitical Impact
  geo: [
    "Crude oil price swings affect India disproportionately since the country imports over 80% of its crude oil needs.",
    "A weaker rupee makes imports (like oil and electronics) costlier but can make Indian exports more competitive globally.",
    "Changes in US Federal Reserve interest rates often influence foreign fund flows into emerging markets like India.",
    "India's trade relationships with major partners like the US, China, and the EU directly affect sectors from IT services to pharmaceuticals to textiles.",
    "Geopolitical tensions in oil-producing regions can spike crude prices, which often pressures Indian inflation and the rupee simultaneously.",
    "China's economic slowdown or recovery can shift global commodity demand, affecting prices for metals and materials that Indian companies rely on.",
    "Tariffs imposed by one country on another's goods can create both risks (for exporters facing the tariff) and opportunities (for competitors who gain market share).",
    "Gold prices often rise during global uncertainty as investors seek 'safe haven' assets, which can affect India's import bill given its large gold demand.",
    "India's IT services sector earns a large share of revenue from US and European clients, making it sensitive to economic conditions in those regions.",
    "Supply chain shifts - companies moving manufacturing away from one country to another - have positioned India as an alternative hub for some global manufacturers.",
  ],

  // Impact Calculator
  calculator: [
    "Even a modest 1% rise in annual inflation can meaningfully erode the real value of a fixed monthly budget over just a few years.",
    "A 0.25% (25 basis point) change in your home loan interest rate can shift your EMI by a noticeable amount over a 20-year tenure.",
    "Fuel prices in India are influenced by global crude oil prices, the rupee-dollar exchange rate, and central/state taxes - all three can move independently.",
    "'Real return' is your investment return minus inflation - a 7% fixed deposit return during 6% inflation leaves you only about 1% richer in real terms.",
    "Small recurring expenses - like a daily ₹50 coffee - add up to over ₹18,000 a year, illustrating how 'small' costs compound.",
    "A rupee depreciation of even a few percent against the dollar can raise the cost of imported goods like electronics, edible oils, and crude-linked products.",
    "Loan tenure has a bigger impact on total interest paid than most borrowers expect - extending a loan by a few years can substantially increase total interest, even if the EMI feels more affordable.",
    "Prepaying even a small extra amount toward loan principal early in the tenure can significantly reduce total interest paid over the life of the loan.",
    "Basis points (bps) are a common way to describe small interest rate changes - 100 basis points equals 1 percentage point.",
    "Budgeting for inflation in long-term goals (like retirement) means the 'number' you need today will look very different - and larger - by the time you reach that goal.",
  ],
};

/**
 * Returns today's fun fact for a given section, using the same
 * deterministic day-of-year approach as the global fun fact bar.
 * An offset per section ensures different sections don't all show
 * a fact from the same index on a given day.
 */
function getDailySectionFact(section) {
  const facts = SECTION_FUN_FACTS[section];
  if (!facts || !facts.length) return "";

  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 0);
  const diff = now - start;
  const dayOfYear = Math.floor(diff / (1000 * 60 * 60 * 24));

  // Small per-section offset so sections rotate independently
  let offset = 0;
  for (let i = 0; i < section.length; i++) offset += section.charCodeAt(i);

  return facts[(dayOfYear + offset) % facts.length];
}

/**
 * Populates a "Did You Know?" fun fact element for a given section.
 * Looks for an element with id `funFact-<section>`.
 */
function loadSectionFunFact(section) {
  const el = document.getElementById(`funFact-${section}`);
  if (!el) return;
  const fact = getDailySectionFact(section);
  if (fact) el.textContent = fact;
}
