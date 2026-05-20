"""
Monad blockchain anchoring for TrapRoyalties.
Writes SHA-256 hashes on-chain at two points:
  1. Artist face scan complete  → anchors biometric identity hash
  2. PDF download triggered     → anchors PDF document hash

Contract assumed ABI: anchor(bytes32 hash, string metadata)
"""

import os, json, datetime
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

RPC_URL          = os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
CHAIN_ID         = int(os.getenv("MONAD_CHAIN_ID", "10143"))
CONTRACT_ADDRESS = os.getenv("MONAD_CONTRACT", "0xAa19bFC7Bd852efe49ef31297bB082FB044B2ea4")
PRIVATE_KEY      = os.getenv("MONAD_PRIVATE_KEY", "")

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "hash",     "type": "bytes32"},
            {"internalType": "string",  "name": "metadata", "type": "string"},
        ],
        "name": "anchor",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


def _w3():
    return Web3(Web3.HTTPProvider(RPC_URL))


def anchor_hash(sha256_hex: str, metadata: dict) -> dict:
    """
    Write sha256_hex on-chain with JSON metadata.
    Returns {"tx": "0x...", "block": N} on success or {"error": "..."} on failure.
    """
    if not PRIVATE_KEY:
        return {"error": "MONAD_PRIVATE_KEY not set"}

    try:
        w3 = _w3()
        if not w3.is_connected():
            return {"error": "Cannot connect to Monad RPC"}

        account  = w3.eth.account.from_key(PRIVATE_KEY)
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACT_ADDRESS),
            abi=CONTRACT_ABI,
        )

        # bytes32 expects exactly 32 bytes
        hash_bytes = bytes.fromhex(sha256_hex)[:32]
        meta_str   = json.dumps(metadata, separators=(",", ":"))

        nonce = w3.eth.get_transaction_count(account.address)
        gas_price = w3.eth.gas_price

        tx = contract.functions.anchor(hash_bytes, meta_str).build_transaction({
            "chainId":  CHAIN_ID,
            "from":     account.address,
            "nonce":    nonce,
            "gasPrice": gas_price,
            "gas":      200_000,
        })

        signed  = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        return {
            "tx":    receipt.transactionHash.hex(),
            "block": receipt.blockNumber,
            "status": receipt.status,  # 1 = success
        }

    except Exception as e:
        return {"error": str(e)}


def anchor_scan(audit_id: str, artist: str, track: str, sha256_hex: str) -> dict:
    """Anchor a biometric scan identity hash."""
    metadata = {
        "type":      "BIOMETRIC_SCAN",
        "audit_id":  audit_id,
        "artist":    artist,
        "track":     track,
        "sha256":    sha256_hex,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    return anchor_hash(sha256_hex, metadata)


def anchor_pdf(audit_id: str, artist: str, track: str, isrc: str, sha256_hex: str) -> dict:
    """Anchor a certified PDF document hash."""
    metadata = {
        "type":      "PDF_CERTIFIED",
        "audit_id":  audit_id,
        "artist":    artist,
        "track":     track,
        "isrc":      isrc,
        "sha256":    sha256_hex,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }
    return anchor_hash(sha256_hex, metadata)
