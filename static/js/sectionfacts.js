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

  // ---- BONUS FACTS (added batch 2 — 10 per existing section) ----
  // These extend each array so getDailySectionFact() cycles through more variety.
  // Appended after original arrays by merging at runtime in getDailySectionFact()
};

// Extra facts added in batch 2 — merged into SECTION_FUN_FACTS at load time
const SECTION_FUN_FACTS_EXTRA = {
  dashboard: [
    "India's Unified Payments Interface (UPI) now processes over 10 billion transactions a month — a feat that has global fintech companies studying it as a model.",
    "SEBI introduced the T+1 settlement cycle for stocks — meaning trade settlement in India is now faster than most developed markets, including the US.",
    "The Bombay Stock Exchange's MarketCap is now among the top 10 globally, reflecting India's rapid economic rise over the past three decades.",
    "A 'limit order' lets you set the exact price at which you want to buy or sell a stock, while a 'market order' executes at the current best available price.",
    "India's 'Amrit Kaal' vision targets a $30 trillion economy by 2047 — one of the most ambitious national economic goals globally.",
    "The NSE's trading system handles millions of orders per second and is considered one of the fastest and most reliable exchanges in the world.",
    "Algorithmic trading now accounts for a significant portion of daily volume on Indian exchanges — automated systems place orders in microseconds.",
    "SEBI mandates that listed companies hold at least one Annual General Meeting (AGM) each year where shareholders can ask questions of management.",
    "'Pledging' of shares happens when a promoter borrows money by pledging their own shares as collateral — high promoter pledging can be a warning sign.",
    "India introduced 'Sovereign Gold Bonds' (SGBs) to offer a paper-gold investment with interest, reducing physical gold demand and easing import pressure.",
  ],
  stock: [
    "A 'moat' is Warren Buffett's term for a company's durable competitive advantage — pricing power, brand loyalty, or switching costs that protect profits from rivals.",
    "'Free cash flow' (FCF) is what a company has left after paying all expenses and investments — often considered more reliable than reported profits.",
    "The Altman Z-Score is a formula using five financial ratios to predict the probability that a company will go bankrupt within two years.",
    "'Earnings surprise' occurs when a company reports profit above or below analyst estimates — positive surprises often trigger sharp single-day rallies.",
    "A company's 'inventory turnover' ratio shows how many times it sells and restocks goods in a period — higher is generally better for efficiency.",
    "The 'quick ratio' (or acid-test ratio) measures a company's ability to cover short-term liabilities using only its most liquid assets, excluding inventory.",
    "In India, shares go 'ex-dividend' typically one trading day before the record date — buying on or after the ex-date means you don't receive that dividend.",
    "'Quantitative easing' (QE) by global central banks can push money into emerging markets like India, boosting stock prices — and its reversal can pull it out.",
    "A company can 'buyback' its shares via a tender offer (fixed price) or open-market purchases — both reduce share count and can lift earnings per share.",
    "When FIIs sell heavily in Indian markets, DIIs (LIC, mutual funds) often step in as 'buyers of last resort,' providing a floor during sharp corrections.",
  ],
  market: [
    "The 'Advance-Decline ratio' compares the number of stocks rising versus falling on a given day — a broad signal of market health beyond the headline index.",
    "Circuit breakers on Indian exchanges halt trading for 15 minutes at a 10% move, 45 minutes at 15%, and the rest of the day at a 20% move in the Nifty.",
    "Nifty 50 and Sensex futures trade on exchanges and let investors speculate on or hedge against index moves without owning individual stocks.",
    "Options contracts give buyers the right (but not the obligation) to buy or sell shares at a set price — a staple of derivatives trading in India.",
    "India's 'rollover' in futures markets (near-month to next-month) happens in the last week of each month and often causes brief spikes in volatility.",
    "The 'put-call ratio' (PCR) in options data is closely watched as a contrarian sentiment indicator — very high put buying can sometimes signal a market bottom.",
    "Foreign Portfolio Investors (FPIs) hold a significant share of many large Indian companies — their flows are publicly disclosed to SEBI and widely tracked.",
    "India's 'participation certificates' (P-notes) allowed overseas investors to invest indirectly in Indian securities without direct SEBI registration.",
    "Quarterly results announcements often lead to 'buy the rumour, sell the news' patterns — stocks sometimes fall even on good earnings if expectations were higher.",
    "The 'fear index' India VIX spikes during events like election results, RBI policy announcements, and global market crises, then typically reverts afterward.",
  ],
  mutualfunds: [
    "AMFI's 'Mutual Funds Sahi Hai' campaign helped triple the number of SIP accounts in India in just a few years after its launch.",
    "A 'fund of funds' (FoF) invests in other mutual funds rather than directly in stocks or bonds — useful for accessing international markets from India.",
    "Debt mutual funds in India were reclassified under tax rules in 2023, removing the indexation benefit that had made them attractive to conservative investors.",
    "The 'Sharpe ratio' of a mutual fund measures return per unit of risk — a higher number means you're being compensated better for the volatility you're taking on.",
    "SIP 'top-up' allows you to automatically increase your SIP amount each year — aligning your investments with salary growth is a powerful long-term strategy.",
    "In a 'dividend option' of a mutual fund, profits are distributed periodically; in a 'growth option,' they are reinvested — growth typically outperforms long-term.",
    "The 'tracking error' of an index fund shows how closely it follows its benchmark — a lower tracking error means the fund is doing its job more faithfully.",
    "Flexi-cap funds can invest across large, mid, and small caps with no fixed allocation — giving fund managers maximum flexibility to adapt to market conditions.",
    "India's mutual fund industry is regulated under SEBI's 'Categorization and Rationalization' circular, which standardized fund categories to reduce investor confusion.",
    "Liquid funds invest in very short-term instruments and are often used as a cash-management tool — they can be redeemed with money typically arriving the next day.",
  ],
  macro: [
    "India's 'demographic dividend' — a large working-age population — is expected to continue boosting economic growth well into the 2040s if fully employed.",
    "The current account deficit (CAD) is funded by capital inflows like FDI and FPI — when those dry up, the rupee comes under significant pressure.",
    "India's Union Budget sets the fiscal deficit target as a percentage of GDP — a larger deficit can crowd out private investment or increase inflation.",
    "The 'twin deficit' — simultaneous fiscal and current account deficits — is a vulnerability sometimes associated with pressure on the rupee and inflation.",
    "India's infrastructure spending has grown sharply in recent years, with roads, railways, and ports seen as key multipliers of broader economic growth.",
    "The 'multiplier effect' means that government infrastructure spending tends to generate more than ₹1 of economic activity per ₹1 spent, as it creates jobs and demand.",
    "India's GST collection is a real-time indicator of economic health — consistently above ₹1.5 lakh crore monthly is considered a sign of robust activity.",
    "The 'output gap' measures how far actual GDP is from its potential — a negative gap means the economy is underperforming its capacity, justifying stimulus.",
    "India's state governments also borrow from markets (through SDL — State Development Loans), and their fiscal health contributes to overall sovereign risk.",
    "External debt denominated in foreign currency creates repayment risk if the rupee weakens sharply — India keeps its external debt at relatively manageable levels.",
  ],
  inflation: [
    "Monsoon patterns directly affect food inflation in India since about half the country's farmland depends on rain-fed irrigation.",
    "Fuel inflation in India is heavily influenced by global crude oil prices, the rupee-dollar exchange rate, and both central and state government tax structures.",
    "The RBI's 'flexible inflation targeting' framework requires it to explain in writing to the government if CPI stays outside the 2-6% band for three consecutive quarters.",
    "Stagflation — high inflation combined with slow growth — is particularly challenging for central banks since rate hikes that fight inflation also suppress growth.",
    "'Imported inflation' occurs when price rises abroad flow into India through the cost of imports — crude oil and edible oils are common channels.",
    "Household inflation expectations, surveyed by the RBI regularly, influence wage demands and pricing decisions — central banks track them alongside the official CPI.",
    "India's food inflation is split into 'vegetables' (highly volatile, seasonal) and 'cereals/pulses' (more persistent) — the RBI looks through the former but worries about the latter.",
    "Real interest rates (nominal rates minus inflation) matter for investment decisions — when real rates are very negative, investors tend to move into real assets like gold or property.",
    "The 'base effect' means that high inflation months last year make this year's year-on-year comparison look lower — and vice versa — even if actual prices haven't changed much.",
    "Core services inflation has been sticky globally post-pandemic, driven by wage growth — the RBI watches this component carefully even when headline numbers soften.",
  ],
  tax: [
    "India's 'faceless assessment' scheme, introduced in 2020, removes the physical interface between taxpayers and tax officers — aiming to reduce harassment and improve transparency.",
    "Capital gains tax in India depends on both the asset class (equity, debt, property) and the holding period (short-term vs. long-term), with different rates for each combination.",
    "The 'presumptive taxation scheme' lets small businesses and professionals pay tax on a flat percentage of turnover without maintaining detailed books of accounts.",
    "Agricultural income is exempt from income tax in India — but it is added to other income for the purpose of determining the applicable tax slab rate.",
    "The GST council, chaired by the Union Finance Minister with state finance ministers as members, meets periodically to revise rates and resolve disputes.",
    "India's 'LTCG' (long-term capital gains) tax on equity, reintroduced in 2018, applies above ₹1 lakh of gains per year — gains below this threshold remain tax-free.",
    "The 'Securities Transaction Tax' (STT) is levied on equity trades and options/futures transactions — it is collected at source and cannot be avoided.",
    "An 'HUF' (Hindu Undivided Family) is a separate legal entity for tax purposes in India, allowing a family to hold assets and earn income under a separate PAN.",
    "Tax loss harvesting — deliberately selling underperforming investments to realise a capital loss that offsets taxable gains — is a legal strategy to reduce your tax bill.",
    "NRIs (Non-Resident Indians) are taxed in India only on income 'accruing or arising' in India — overseas income is generally not taxable in India for NRIs.",
  ],
  business: [
    "India's 'PLI' (Production-Linked Incentive) schemes have attracted large investments in sectors like semiconductors, mobile phones, and EVs from both domestic and global companies.",
    "A 'rights issue' at a steep discount to market price can be dilutive for shareholders who don't participate — understanding the ex-rights price calculation matters.",
    "Listed companies in India must disclose any material information (big contracts, management changes, litigation) to the exchanges within 24 hours under SEBI's LODR regulations.",
    "The 'debt-to-EBITDA' ratio is widely used by credit analysts — a ratio above 3-4x is often considered a warning sign of over-leverage in cyclical industries.",
    "India's startup ecosystem has produced over 100 unicorns — privately held companies valued at over $1 billion — making it one of the world's largest such ecosystems.",
    "Dividend payout ratio measures what fraction of net profit a company distributes as dividends — a very high ratio may not be sustainable if earnings are volatile.",
    "Promoter shareholding above 50% means the controlling group can pass ordinary resolutions without minority shareholder support — governance matters more in such companies.",
    "A company 'going dark' (delisting from exchanges) removes it from public markets — SEBI mandates a delisting price floor based on a formula to protect minority shareholders.",
    "India's 'Insolvency and Bankruptcy Code' (IBC), introduced in 2016, significantly improved the speed of debt resolution and has changed how lenders view large corporate defaulters.",
    "A company's ESG (Environmental, Social, Governance) score is increasingly influencing institutional investment decisions — poor ESG ratings can raise a company's cost of capital.",
  ],
  geo: [
    "India is the world's third-largest oil importer — a $10 rise in global crude oil prices can increase India's annual import bill by roughly $12-15 billion.",
    "India's IT sector exports exceed $200 billion annually, making it one of the country's largest foreign exchange earners and a key buffer for the current account.",
    "Trade agreements (like CEPA with UAE and FTA with Australia) directly affect tariffs on Indian exports and imports, reshaping competitiveness across sectors.",
    "China's moves in the South China Sea and Taiwan Strait create supply chain risk for global electronics — India has positioned itself as an alternative manufacturing hub.",
    "Russia's war in Ukraine disrupted global wheat and fertiliser supply chains, both of which affect Indian agriculture and food inflation.",
    "Dollar strength (DXY rising) typically pressures emerging market currencies including the rupee, raises India's import bill, and can trigger FII outflows.",
    "India's 'Act East' policy has deepened trade ties with Southeast Asia, opening new export markets and creating supply chain partnerships for Indian manufacturers.",
    "Geopolitical tensions often push investors toward 'safe havens' like US Treasuries and gold — both can temporarily drain capital from Indian equity and debt markets.",
    "India's diaspora remittances (over $100 billion annually) are a major and relatively stable source of foreign exchange, helping support the rupee during global turbulence.",
    "Changes in US immigration policy can affect India's large IT services workforce — visa restrictions raise delivery costs for Indian IT companies with US clients.",
  ],
  calculator: [
    "Compound interest is famously described as the 'eighth wonder of the world' — a ₹10,000 monthly SIP earning 12% annually becomes over ₹3.5 crore in 30 years.",
    "The 'Rule of 72' is a quick mental math trick: divide 72 by your annual return rate to estimate how many years it takes to double your money.",
    "Inflation of just 6% per year halves the purchasing power of ₹1 lakh in approximately 12 years — making inflation adjustment essential in any long-term financial plan.",
    "For a ₹50 lakh home loan at 9% over 20 years, the total interest paid exceeds the principal — you pay more than ₹50 lakh in interest alone.",
    "Petrol prices in India include central excise duty and state VAT — these taxes can together account for nearly half the pump price, insulating (and sometimes amplifying) consumers from crude price moves.",
    "A salary hike of 10% on a ₹1 lakh monthly income adds ₹1.2 lakh per year before tax — but your effective take-home increase is lower after accounting for the higher tax bracket.",
    "If the rupee depreciates by 5% against the dollar, your international holiday budget or overseas education cost increases by roughly the same amount in rupee terms.",
    "Prepaying ₹1 lakh on a home loan early in the tenure can save 3-5 times that amount in total interest over the remaining loan period.",
    "Health insurance premiums typically rise 15-20% annually in India — factoring this cost inflation into your long-term budget is as important as planning for general inflation.",
    "A 1% higher expense ratio on a ₹10 lakh mutual fund investment compounding at 12% over 20 years costs you approximately ₹6.5 lakh in foregone returns.",
  ],
};

// Merge extra facts into the main SECTION_FUN_FACTS object at load time
Object.keys(SECTION_FUN_FACTS_EXTRA).forEach(section => {
  if (SECTION_FUN_FACTS[section]) {
    SECTION_FUN_FACTS[section] = SECTION_FUN_FACTS[section].concat(SECTION_FUN_FACTS_EXTRA[section]);
  }
});

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
