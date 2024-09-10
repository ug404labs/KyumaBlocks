// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";

contract KyumaBlocks is ERC20, Ownable {
    using Counters for Counters.Counter;

    struct User {
        bool isRegistered;
        uint256 reputation;
        uint256 recycledAmount;
    }

    struct Buyer {
        string name;
        bool isVerified;
        string location;
        string additionalInfo;
    }

    struct EWaste {
        address recycler;
        string description;
        uint256 weight;
        bool isCollected;
        bool isProcessed;
    }

    struct Errand {
        address runner;
        address creator;
        string description;
        uint256 reward;
        bool isCompleted;
    }

    mapping(address => User) public users;
    mapping(address => Buyer) public buyers;

    Counters.Counter private _eWasteIdCounter;
    mapping(uint256 => EWaste) public eWastes;

    Counters.Counter private _errandIdCounter;
    mapping(uint256 => Errand) public errands;

    event UserRegistered(address indexed user);
    event BuyerRegistered(address indexed buyer, string name);
    event EWasteRecycled(uint256 indexed id, address indexed recycler, uint256 weight);
    event ErrandCreated(uint256 indexed id, address indexed creator, uint256 reward);
    event ErrandCompleted(uint256 indexed id, address indexed runner);

    constructor() ERC20("Kyuma Blocks Token", "KBT") {
        _mint(msg.sender, 1000000 * 10**decimals());
    }

    function registerUser() external {
        require(!users[msg.sender].isRegistered, "User already registered");
        users[msg.sender] = User(true, 0, 0);
        emit UserRegistered(msg.sender);
    }

    function registerBuyer(string memory name, string memory location, string memory additionalInfo) external {
        require(!buyers[msg.sender].isVerified, "Buyer already registered");
        buyers[msg.sender] = Buyer(name, true, location, additionalInfo);
        emit BuyerRegistered(msg.sender, name);
    }

    function recycleEWaste(string memory description, uint256 weight) external {
        require(users[msg.sender].isRegistered, "User not registered");
        uint256 eWasteId = _eWasteIdCounter.current();
        eWastes[eWasteId] = EWaste(msg.sender, description, weight, false, false);
        _eWasteIdCounter.increment();

        users[msg.sender].recycledAmount += weight;
        users[msg.sender].reputation += 1;

        uint256 reward = weight * 10; // 10 tokens per unit of weight
        _mint(msg.sender, reward);

        emit EWasteRecycled(eWasteId, msg.sender, weight);
    }

    function createErrand(string memory description, uint256 reward) external {
        require(users[msg.sender].isRegistered, "User not registered");
        require(balanceOf(msg.sender) >= reward, "Insufficient balance for reward");

        uint256 errandId = _errandIdCounter.current();
        errands[errandId] = Errand(address(0), msg.sender, description, reward, false);
        _errandIdCounter.increment();

        _transfer(msg.sender, address(this), reward);

        emit ErrandCreated(errandId, msg.sender, reward);
    }

    function completeErrand(uint256 errandId) external {
        require(users[msg.sender].isRegistered, "User not registered");
        Errand storage errand = errands[errandId];
        require(!errand.isCompleted, "Errand already completed");
        require(errand.runner == address(0), "Errand already assigned");

        errand.runner = msg.sender;
        errand.isCompleted = true;

        _transfer(address(this), msg.sender, errand.reward);
        users[msg.sender].reputation += 1;

        emit ErrandCompleted(errandId, msg.sender);
    }

    function verifyBuyer(address buyerAddress) external onlyOwner {
        require(buyers[buyerAddress].isVerified == false, "Buyer already verified");
        buyers[buyerAddress].isVerified = true;
    }

    function processEWaste(uint256 eWasteId) external {
        require(buyers[msg.sender].isVerified, "Not a verified buyer");
        EWaste storage eWaste = eWastes[eWasteId];
        require(!eWaste.isProcessed, "E-Waste already processed");

        eWaste.isProcessed = true;
        users[eWaste.recycler].reputation += 2;
    }

    function payForEWaste(address recycler, uint256 amount) external {
        require(buyers[msg.sender].isVerified, "Not a verified buyer");
        require(balanceOf(msg.sender) >= amount, "Insufficient balance");

        _transfer(msg.sender, recycler, amount);
    }

    function getUserReputation(address user) external view returns (uint256) {
        return users[user].reputation;
    }

    function getUserRecycledAmount(address user) external view returns (uint256) {
        return users[user].recycledAmount;
    }

    function getBuyerInfo(address buyer) external view returns (string memory, bool, string memory, string memory) {
        Buyer memory buyerInfo = buyers[buyer];
        return (buyerInfo.name, buyerInfo.isVerified, buyerInfo.location, buyerInfo.additionalInfo);
    }
}