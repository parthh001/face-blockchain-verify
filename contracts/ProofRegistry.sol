// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title ProofRegistry
/// @notice Anchors a hash/fingerprint of off-chain discovered data (a face
/// encoding fingerprint + the social media post it was matched to) so it
/// can be re-verified later against an immutable on-chain record.
/// This is the optional "real testnet" backend for the pipeline -- the
/// default backend (src/simple_chain.py) does the same job on a local
/// simulated chain and needs no wallet, RPC, or gas.
contract ProofRegistry {
    struct Record {
        bytes32 dataHash;      // sha256 of the canonical JSON record
        string metadataURI;    // e.g. the matched social media post URL
        address submitter;
        uint256 timestamp;
        bool exists;
    }

    // dataHash => Record
    mapping(bytes32 => Record) private records;

    event RecordRegistered(bytes32 indexed dataHash, address indexed submitter, string metadataURI, uint256 timestamp);

    /// @notice Register a new tamper-evident record on-chain.
    /// @param dataHash sha256 hash of the off-chain data being anchored.
    /// @param metadataURI human-readable reference (e.g. the social post URL).
    function registerRecord(bytes32 dataHash, string calldata metadataURI) external {
        require(!records[dataHash].exists, "Record already registered");
        records[dataHash] = Record({
            dataHash: dataHash,
            metadataURI: metadataURI,
            submitter: msg.sender,
            timestamp: block.timestamp,
            exists: true
        });
        emit RecordRegistered(dataHash, msg.sender, metadataURI, block.timestamp);
    }

    /// @notice Re-verify a piece of off-chain data against the on-chain record.
    /// @param dataHash sha256 hash recomputed from the data you want to verify.
    /// @return found whether a record with this hash exists on-chain.
    /// @return metadataURI the metadata stored when it was registered.
    /// @return submitter the address that registered it.
    /// @return timestamp the block timestamp it was registered at.
    function verifyRecord(bytes32 dataHash)
        external
        view
        returns (bool found, string memory metadataURI, address submitter, uint256 timestamp)
    {
        Record memory r = records[dataHash];
        return (r.exists, r.metadataURI, r.submitter, r.timestamp);
    }
}
