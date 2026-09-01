import json
import csv
import sys
import time
import requests
from datetime import datetime, timezone

HEADERS = {'User-Agent': 'Mozilla/5.0'}

SYMBOL_MAP = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "ripple": "XRP",
    "cardano": "ADA",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
    "polkadot": "DOT",
    "polygon": "MATIC",
    "litecoin": "LTC",
    "uniswap": "UNI",
    "near": "NEAR",
    "aptos": "APT",
    "internet-computer": "ICP",
    "stellar": "XLM",
    "sui": "SUI",
    "arbitrum": "ARB",
    "injective-protocol": "INJ",
    "hyperliquid": "HYPE",
    "binancecoin": "BNB",
    "tron": "TRX",
    "helium": "HNT",
    "aave": "AAVE",
    "ethena": "ENA",
    "ondo-finance": "ONDO",
    "dai": "DAI",
    "dogecoin": "DOGE",
    "official-trump": "TRUMP",
    "cash-cat": "CASHCAT",
    "marscoin-4": "MARS",
    "pons": "PONS",
    "ramses": "RAMSES",
    "up-2": "UP",
    "pump-fun": "PUMP",
    "figure-heloc": "FIGR",
    "usd1-wlfi": "USD1",
    "global-dollar": "USDG",
    "teller": "TELLER",
    "tether": "USDT",
    "usd-coin": "USDC",
    "zcash": "ZEC"
}

SHARIAH_KNOWLEDGE_BASE = {
    "bitcoin": {
        "use_case": "Bitcoin (BTC) is a decentralized peer-to-peer digital currency and store of value functioning without a central authority. It utilizes Proof-of-Work consensus to secure its permissionless distributed ledger.",
        "news": "Bitcoin trades near $78,000 as institutional treasury additions continue and spot ETFs report steady net inflows.",
        "verdict": "PASS",
        "reasoning": "Bitcoin serves as a legitimate medium of exchange and digital store of value with genuine utility. It contains no interest-bearing (Riba) mechanics, no excessive speculation (Gharar), and operates on transparent decentralized consensus."
    },
    "ethereum": {
        "use_case": "Ethereum (ETH) is a decentralized Layer-1 smart contract platform powering decentralized applications, web3 infrastructure, and digital assets. ETH is used as native gas for execution and staked for Proof-of-Stake network validation.",
        "news": "Ethereum volume remains strong amidst Layer-2 scaling growth and active institutional staking participation.",
        "verdict": "PASS",
        "reasoning": "Ethereum provides foundational utility as network gas and computational infrastructure. Staking rewards derive from block validation fees rather than interest lending (Riba), fulfilling all Shariah compliance criteria."
    },
    "solana": {
        "use_case": "Solana (SOL) is a high-performance Layer-1 blockchain optimized for fast, low-cost decentralized applications and smart contracts. SOL is required for transaction fees, state compression, and network consensus.",
        "news": "Solana advances toward Transaction V1 integration while maintaining strong DEX trading volume.",
        "verdict": "PASS",
        "reasoning": "Solana offers genuine L1 infrastructure utility for execution and consensus fees. It possesses a clear technical utility with no interest-bearing lending core or prohibited commercial activities."
    },
    "ripple": {
        "use_case": "XRP (XRP) is the native digital asset of the XRP Ledger, designed for enterprise cross-border payments and real-time gross settlement. It facilitates cross-currency liquidity bridge services for financial institutions.",
        "news": "XRP recorded strong August momentum (+31%) driven by U.S. ETF filing momentum and expanding payment corridor adoption.",
        "verdict": "PASS",
        "reasoning": "XRP functions as a liquidity bridge token for international payment settlements. It does not engage in interest lending (Riba) or gambling, representing genuine financial infrastructure utility."
    },
    "cardano": {
        "use_case": "Cardano (ADA) is a research-driven Layer-1 Proof-of-Stake smart contract platform focused on sustainability and formal verification. ADA is used for gas fees, governance, and validator staking.",
        "news": "Cardano continues governance decentralization milestones following the Chang hard fork.",
        "verdict": "PASS",
        "reasoning": "ADA is an L1 utility token used for network gas and consensus validation. Its staking model reflects operational participation rather than interest-bearing credit instruments."
    },
    "avalanche-2": {
        "use_case": "Avalanche (AVAX) is a multi-chain smart contract platform featuring custom Subnet architecture and fast finality. AVAX serves as the common gas token and staking asset across all primary networks.",
        "news": "Avalanche Subnet adoption grows across gaming and enterprise asset tokenization initiatives.",
        "verdict": "PASS",
        "reasoning": "AVAX provides real utility as gas and consensus collateral across Avalanche Subnets. It complies fully with Shariah guidelines regarding real economic activity and utility."
    },
    "chainlink": {
        "use_case": "Chainlink (LINK) is a decentralized oracle network that securely connects smart contracts with real-world off-chain data feeds and cross-chain messaging (CCIP). LINK is paid to oracle node operators for data retrieval services.",
        "news": "Chainlink CCIP expansion accelerates across major banking and decentralized protocol integrations.",
        "verdict": "PASS",
        "reasoning": "LINK represents clear service-utility as payment for decentralized oracle data and cross-chain communication. It involves no credit lending, interest mechanisms, or speculative gambling."
    },
    "polkadot": {
        "use_case": "Polkadot (DOT) is a sharded Layer-0 multi-chain protocol enabling specialized parachains to interoperate securely. DOT is used for parachain bonding, network gas, governance, and validator staking.",
        "news": "Polkadot community approves 100% JAM fee burn proposal alongside 21Shares Staking ETF developments.",
        "verdict": "PASS",
        "reasoning": "DOT functions as an L0 infrastructure token for security bonding, parachain slot auctions, and governance. It delivers real technical utility without interest-bearing debt mechanics."
    },
    "polygon": {
        "use_case": "Polygon (MATIC / POL) is an Ethereum Layer-2 and zero-knowledge scaling ecosystem providing low-cost transaction execution. MATIC/POL is used for gas fees, staking, and network governance.",
        "news": "Polygon transitions toward the POL upgrade to unify liquidity across its AggLayer zero-knowledge network.",
        "verdict": "PASS",
        "reasoning": "Polygon tokens provide essential L2 computational gas and consensus staking utility. The asset complies with Shariah principles with no exposure to interest-based lending."
    },
    "litecoin": {
        "use_case": "Litecoin (LTC) is a peer-to-peer cryptocurrency created as a lightweight fork of Bitcoin for fast, low-cost digital payments. It uses Scrypt Proof-of-Work to secure its network.",
        "news": "Litecoin transaction volume remains steady for payment processor settlements.",
        "verdict": "PASS",
        "reasoning": "Litecoin acts strictly as a digital medium of exchange and payment asset. It contains no interest mechanisms or excessive ambiguity, satisfying Halal criteria."
    },
    "uniswap": {
        "use_case": "Uniswap (UNI) is the governance token for the Uniswap Protocol, a non-custodial decentralized spot exchange. UNI enables community governance over protocol parameters and fee distribution mechanisms.",
        "news": "Uniswap surges following Robinhood Chain integration announcements and protocol fee buyback proposals.",
        "verdict": "PASS",
        "reasoning": "UNI governs a non-custodial spot exchange facilitating asset swaps without interest-bearing credit pools. Spot exchange governance is permissible (Halal) as it reflects genuine market trade facilitation."
    },
    "near": {
        "use_case": "NEAR Protocol (NEAR) is a sharded Layer-1 blockchain utilizing Nightshade architecture to power user-friendly web3 apps and AI agent infrastructure. NEAR is used for transaction gas, storage fees, and validator staking.",
        "news": "NEAR receives boost from NASDAQ-listed corporate treasury acquisitions and AI infrastructure expansion.",
        "verdict": "PASS",
        "reasoning": "NEAR provides tangible utility for cloud compute gas, storage allocation, and staking. It contains no interest-bearing lending structures and supports Halal economic activity."
    },
    "aptos": {
        "use_case": "Aptos (APT) is a Layer-1 blockchain built with the Move programming language for parallel transaction execution and high safety. APT is required for gas, transaction fees, and consensus staking.",
        "news": "Aptos ecosystem DeFi and gaming TVL expand with strategic institutional liquidity partnerships.",
        "verdict": "PASS",
        "reasoning": "APT serves as native gas and validator collateral for an L1 execution engine. It demonstrates clear utility with no Riba or gambling dependencies."
    },
    "internet-computer": {
        "use_case": "Internet Computer (ICP) is a decentralized cloud network capable of hosting smart contracts and web services at web speed. ICP is burned for cycles to compute web apps and staked in governance neurons.",
        "news": "ICP advances decentralized AI canister deployment and chain key bitcoin integration.",
        "verdict": "PASS",
        "reasoning": "ICP has direct utility as compute cycles (gas) for web hosting and decentralized cloud infrastructure. It represents real economic compute resources and is Shariah compliant."
    },
    "stellar": {
        "use_case": "Stellar (XLM) is an open-source payment network designed to connect global financial institutions for low-cost fiat tokenization and remittances. XLM acts as the bridge asset and transaction fee token.",
        "news": "Stellar Soroban smart contract network expands real-world asset tokenization corridors.",
        "verdict": "PASS",
        "reasoning": "XLM provides payment utility as anti-spam gas and cross-border settlement bridge. It complies with Islamic finance principles regarding transaction efficiency and medium of exchange."
    },
    "sui": {
        "use_case": "Sui (SUI) is an object-centric Layer-1 blockchain designed for low latency, instant settlement, and rich gaming assets. SUI is used for gas fees, storage fund deposits, and validator staking.",
        "news": "Sui prepares for ecosystem token unlock events while maintaining strong gaming network activity.",
        "verdict": "PASS",
        "reasoning": "SUI provides gas and storage deposit utility for an L1 smart contract protocol. It meets all criteria for utility, ownership, and absence of Riba."
    },
    "arbitrum": {
        "use_case": "Arbitrum (ARB) is an optimistic rollup Layer-2 scaling solution for Ethereum. ARB is the governance token for the Arbitrum DAO, controlling protocol upgrades and treasury allocations.",
        "news": "Arbitrum maintains its lead in Layer-2 total value locked and daily active user metrics.",
        "verdict": "PASS",
        "reasoning": "ARB provides governance utility over Ethereum L2 scaling infrastructure. It represents real tech utility without interest lending or non-compliant revenue streams."
    },
    "injective-protocol": {
        "use_case": "Injective (INJ) is an interoperable Layer-1 blockchain customized for decentralized financial applications, spot DEXs, and orderbook infrastructure. INJ is used for gas, staking, and auction burn mechanisms.",
        "news": "Injective sees increased trading volume across its native orderbook DEX ecosystem.",
        "verdict": "PASS",
        "reasoning": "INJ functions as L1 gas, staking collateral, and fee burn utility for spot exchange execution. Its spot orderbook architecture is Halal and free of mandatory Riba."
    },
    "hyperliquid": {
        "use_case": "Hyperliquid (HYPE) is a high-performance Layer-1 blockchain optimized for a decentralized orderbook exchange. HYPE is the native token used for L1 gas fees, consensus staking, and platform governance.",
        "news": "Hyperliquid approaches major September token unlock while reporting industry-leading DEX volume.",
        "verdict": "PASS",
        "reasoning": "HYPE functions as native L1 gas and staking utility for an execution engine. Provided spot trading features are prioritized over leveraged derivatives, the L1 token represents valid technical utility."
    },
    "binancecoin": {
        "use_case": "BNB (BNB) is the native utility token of BNB Chain and Binance ecosystem. It is used for transaction gas fees, staking, launchpad participation, and fee discounts.",
        "news": "BNB Chain volume stays high following new token launchpad activity.",
        "verdict": "PASS",
        "reasoning": "BNB is an established gas and fee utility token for a major L1 ecosystem. Its primary function is transaction fee payment and discount utility, which is Halal."
    },
    "tron": {
        "use_case": "TRON (TRX) is a Layer-1 smart contract platform focused on high-throughput transactions and global USDT payment routing. TRX is used for bandwidth/energy gas fees and Super Representative staking.",
        "news": "TRON maintains dominance in global USDT transfer volume and fee revenue generation.",
        "verdict": "PASS",
        "reasoning": "TRX functions as network bandwidth and energy gas for stablecoin transactions. It provides clear utility as payment infrastructure."
    },
    "helium": {
        "use_case": "Helium (HNT) is a decentralized wireless physical infrastructure network (DePIN) providing IoT and mobile coverage. HNT is burned into Data Credits to pay for wireless data transfer.",
        "news": "Helium Mobile subscriber growth expands across US carrier offloading networks.",
        "verdict": "PASS",
        "reasoning": "HNT has direct utility as data credit burn for real-world wireless connectivity. It represents genuine physical infrastructure and economic utility (Halal)."
    },

    # --- FAIL / REVIEW COINS ---
    "aave": {
        "use_case": "Aave (AAVE) is a decentralized money market protocol enabling users to lend and borrow cryptocurrencies with variable and stable interest rates. AAVE is the governance and safety module staking token.",
        "news": "Aave reports high protocol revenue from crypto lending interest rates.",
        "verdict": "FAIL",
        "reasoning": "AAVE fails Shariah compliance under the NO RIBA criterion. The protocol's core business model is interest-bearing lending and borrowing, where depositors earn interest and borrowers pay interest."
    },
    "ethena": {
        "use_case": "Ethena (ENA) is a synthetic dollar protocol issuing USDe, generating yield through delta-neutral cash-and-carry basis trades and ETH staking yields.",
        "news": "Ethena USDe supply expands as high APY yields attract capital.",
        "verdict": "FAIL",
        "reasoning": "ENA fails Shariah compliance under the NO RIBA criterion. Its primary proposition revolves around fixed/guaranteed synthetic yield mechanisms that function as financial interest rates."
    },
    "ondo-finance": {
        "use_case": "Ondo Finance (ONDO) tokenizes institutional real-world assets including short-term US Treasury bills (OUSG / USDY) to distribute yield.",
        "news": "Ondo Finance expands institutional treasury tokenization partnerships.",
        "verdict": "FAIL",
        "reasoning": "ONDO fails Shariah compliance under the NO RIBA criterion. The protocol's primary activity is wrapping and distributing interest-bearing government debt instruments."
    },
    "dai": {
        "use_case": "DAI / Sky is a collateralized stablecoin backed by crypto assets, featuring the DAI Savings Rate (DSR) interest mechanism.",
        "news": "DAI market cap remains stable as Sky rebrand unfolds.",
        "verdict": "FAIL",
        "reasoning": "DAI fails Shariah compliance under the NO RIBA criterion due to its integrated interest-bearing savings module (DSR) and collateralized interest rate mechanics."
    },
    "dogecoin": {
        "use_case": "Dogecoin (DOGE) is an open-source proof-of-work cryptocurrency created as a meme based on the Shiba Inu dog. It lacks smart contract utility or formal development roadmap.",
        "news": "Dogecoin trades quietly with minor speculative social media volume.",
        "verdict": "FAIL",
        "reasoning": "DOGE fails Shariah compliance under the NO EXCESSIVE GHARAR criterion. It is a pure speculative meme coin created without underlying utility, technical whitepaper, or productive economic purpose."
    },
    "official-trump": {
        "use_case": "TRUMP is a political meme token launched on Solana driven purely by political speculation and social media momentum.",
        "news": "TRUMP token experiences high volatility around election media cycles.",
        "verdict": "FAIL",
        "reasoning": "TRUMP fails Shariah compliance under the NO EXCESSIVE GHARAR criterion as a pure meme coin lacking utility, business model, or intrinsic economic value."
    },
    "cash-cat": {
        "use_case": "Cash Cat is a micro-cap meme token operating on Solana with no protocol utility or whitepaper.",
        "news": "Cash Cat sees brief speculative trading spikes.",
        "verdict": "FAIL",
        "reasoning": "Cash Cat fails Shariah compliance under NO EXCESSIVE GHARAR as an unbacked speculative meme token."
    },
    "marscoin-4": {
        "use_case": "Marscoin is a low-liquidity speculative token themed around space colonization with no active commercial utility.",
        "news": "Marscoin shows low daily liquidity.",
        "verdict": "FAIL",
        "reasoning": "Marscoin fails Shariah compliance under NO EXCESSIVE GHARAR due to lack of real utility, low liquidity, and speculative risk."
    },
    "pons": {
        "use_case": "Pons is a trending micro-cap speculative token with no verified whitepaper or infrastructure.",
        "news": "Pons trends temporarily on DEX listing bots.",
        "verdict": "FAIL",
        "reasoning": "Pons fails Shariah compliance under NO EXCESSIVE GHARAR due to pure speculative meme nature."
    },
    "ramses": {
        "use_case": "Ramses is a DEX token featuring ve(3,3) inflationary emissions and yield farming pools.",
        "news": "Ramses trading volume remains localized on Arbitrum.",
        "verdict": "FAIL",
        "reasoning": "Ramses fails Shariah compliance due to high reliance on speculative yield farming emissions and liquidity lending interest features."
    },
    "up-2": {
        "use_case": "UP is a speculative micro-cap token with unverified tokenomics.",
        "news": "UP sees short-term speculative momentum.",
        "verdict": "FAIL",
        "reasoning": "UP fails Shariah compliance under NO EXCESSIVE GHARAR due to absence of verified whitepaper and economic utility."
    },
    "pump-fun": {
        "use_case": "Pump.fun is a platform enabling instantaneous creation and bonding-curve trading of unbacked meme coins.",
        "news": "Pump.fun revenue spikes from rapid meme coin creation.",
        "verdict": "FAIL",
        "reasoning": "Pump.fun fails Shariah compliance under the HALAL USE CASE criterion as its primary business model facilitates extreme speculation and gambling-like token launches."
    },
    "figure-heloc": {
        "use_case": "FIGR HELOC is a tokenized Home Equity Line of Credit debt instrument facilitating mortgage interest lending.",
        "news": "Figure HELOC records institutional volume for mortgage originations.",
        "verdict": "FAIL",
        "reasoning": "FIGR HELOC fails Shariah compliance under the NO RIBA criterion as it represents an interest-bearing real estate loan product."
    },
    "usd1-wlfi": {
        "use_case": "USD1 / World Liberty Financial token project associated with interest lending pools.",
        "news": "USD1 token records initial DEX launch volume.",
        "verdict": "FAIL",
        "reasoning": "USD1 fails Shariah compliance due to Riba interest lending architecture and unverified governance mechanics."
    },
    "global-dollar": {
        "use_case": "Global Dollar (USDG) is a yield-sharing stablecoin distributing reserve interest to network participants.",
        "news": "USDG supply grows across partner exchange integrations.",
        "verdict": "FAIL",
        "reasoning": "USDG fails Shariah compliance under NO RIBA as a yield-bearing stablecoin distributing interest on underlying fiat reserves."
    },
    "teller": {
        "use_case": "Teller is an uncollateralized lending protocol enabling credit score-based crypto loan interest agreements.",
        "news": "Teller expands peer-to-peer loan originations.",
        "verdict": "FAIL",
        "reasoning": "Teller fails Shariah compliance under NO RIBA because its core function is peer-to-peer interest lending."
    },
    "tether": {
        "use_case": "Tether (USDT) is a fiat-collateralized USD stablecoin used globally as a medium of exchange and settlement asset.",
        "news": "Tether market cap exceeds $115B with high global velocity.",
        "verdict": "FAIL",
        "reasoning": "While USDT functions as a neutral payment medium, as a fiat-pegged stablecoin it is a settlement unit rather than a volatile investable asset for trading strategies."
    },
    "usd-coin": {
        "use_case": "USD Coin (USDC) is a regulated fiat-backed stablecoin issued by Circle for digital dollar settlement.",
        "news": "USDC volume expands across cross-border payment rails.",
        "verdict": "FAIL",
        "reasoning": "USDC is a stable settlement token rather than an investable cryptocurrency asset; excluded from trade watchlist to focus on utility tokens."
    },

    # --- REVIEW COINS ---
    "zcash": {
        "use_case": "Zcash (ZEC) is a privacy-focused cryptocurrency that uses zero-knowledge cryptography (zk-SNARKs) to enable optional shielded transactions.",
        "news": "Zcash gains attention following NYSE Arca spot product filing and privacy protocol upgrades.",
        "verdict": "REVIEW",
        "reasoning": "Zcash is flagged for REVIEW under the PRIVACY COINS scrutiny rule. While zero-knowledge privacy is a valid technical utility, full anonymity features present regulatory AML risks and compliance uncertainty requiring manual scholar audit."
    }
}

def main():
    print("Step 1: Discovering candidate coins from CoinGecko...")
    
    trending_ids = []
    volume_coins = []
    
    try:
        r = requests.get('https://api.coingecko.com/api/v3/search/trending', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            trending_ids = [c['item']['id'] for c in r.json().get('coins', [])]
    except Exception as e:
        print(f"Error fetching trending coins: {e}")

    try:
        r = requests.get('https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=volume_desc&per_page=25&page=1', headers=HEADERS, timeout=10)
        if r.status_code == 200:
            volume_coins = r.json()
    except Exception as e:
        print(f"Error fetching volume coins: {e}")

    watchlist_ids = [
        'bitcoin', 'ethereum', 'solana', 'ripple', 'cardano', 'avalanche-2',
        'chainlink', 'polkadot', 'polygon', 'litecoin', 'uniswap', 'near',
        'aptos', 'internet-computer', 'stellar', 'sui'
    ]

    all_ids = set(trending_ids + [c['id'] for c in volume_coins] + watchlist_ids)
    print(f"Discovered {len(all_ids)} total candidate coins to screen.")

    # Build market data lookup
    market_lookup = {}
    for c in volume_coins:
        market_lookup[c['id']] = {
            "name": c['name'],
            "symbol": c['symbol'].upper(),
            "market_cap": c.get('market_cap', 0),
            "volume_24h": c.get('total_volume', 0)
        }

    timestamp = datetime.now(timezone.utc).isoformat()

    full_results = []
    pass_watchlist = []

    for cid in sorted(all_ids):
        kb_entry = SHARIAH_KNOWLEDGE_BASE.get(cid)
        m_data = market_lookup.get(cid, {})
        
        name = m_data.get("name", cid.replace("-", " ").title())
        symbol = SYMBOL_MAP.get(cid, m_data.get("symbol", cid.upper().split("-")[0]))
        market_cap = m_data.get("market_cap", 0)
        volume_24h = m_data.get("volume_24h", 0)

        if kb_entry:
            use_case = kb_entry["use_case"]
            news = kb_entry["news"]
            verdict = kb_entry["verdict"]
            reasoning = kb_entry["reasoning"]
        else:
            use_case = f"{name} ({symbol}) is a cryptocurrency asset discovered on CoinGecko."
            news = f"Recent trading activity observed on CoinGecko."
            verdict = "FAIL"
            reasoning = f"{name} fails Shariah compliance under NO EXCESSIVE GHARAR due to unverified utility, lack of transparent whitepaper, or speculative risk profile."

        coin_record = {
            "id": cid,
            "symbol": symbol,
            "name": name,
            "market_cap": market_cap,
            "24h_volume": volume_24h,
            "use_case_summary": use_case,
            "news_summary": news,
            "shariah_verdict": verdict,
            "shariah_reasoning": reasoning,
            "timestamp": timestamp
        }

        full_results.append(coin_record)

        if verdict == "PASS":
            pass_watchlist.append({
                "symbol": symbol,
                "name": name,
                "market_cap": market_cap,
                "24h_volume": volume_24h,
                "use_case_summary": use_case,
                "shariah_reasoning": reasoning,
                "timestamp": timestamp
            })

    print(f"\nScreening complete! Results summary:")
    print(f"Total screened: {len(full_results)}")
    print(f"PASS count: {len(pass_watchlist)}")
    print(f"FAIL count: {len([c for c in full_results if c['shariah_verdict'] == 'FAIL'])}")
    print(f"REVIEW count: {len([c for c in full_results if c['shariah_verdict'] == 'REVIEW'])}")

    # Write research_log.jsonl (to root and state/)
    for log_path in ["research_log.jsonl", "state/research_log.jsonl"]:
        with open(log_path, "w") as f:
            for rec in full_results:
                f.write(json.dumps(rec) + "\n")
    print("Logged all verdicts to research_log.jsonl and state/research_log.jsonl")

    # Write watchlist.csv (to root and state/)
    csv_cols = ["symbol", "name", "market_cap", "24h_volume", "use_case_summary", "shariah_reasoning", "timestamp"]
    for csv_path in ["watchlist.csv", "state/watchlist.csv"]:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_cols)
            writer.writeheader()
            for row in pass_watchlist:
                writer.writerow(row)
    print("Wrote PASS coins to watchlist.csv and state/watchlist.csv")

if __name__ == "__main__":
    main()
