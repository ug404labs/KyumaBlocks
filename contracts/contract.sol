// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract KyumaBlocks {
    string public name = "Kyuma Blocks Token";
    string public symbol = "KBT";
    uint8 public decimals = 18;
    uint256 public totalSupply;
    address public owner;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

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

    uint256 private _eWasteIdCounter;
    mapping(uint256 => EWaste) public eWastes;

    uint256 private _errandIdCounter;
    mapping(uint256 => Errand) public errands;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event UserRegistered(address indexed user);
    event BuyerRegistered(address indexed buyer, string name);
    event EWasteRecycled(uint256 indexed id, address indexed recycler, uint256 weight);
    event ErrandCreated(uint256 indexed id, address indexed creator, uint256 reward);
    event ErrandCompleted(uint256 indexed id, address indexed runner);

    constructor() {
        owner = msg.sender;
        totalSupply = 1000000 * 10**uint256(decimals);
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not the owner");
        _;
    }

    function transfer(address to, uint256 value) public returns (bool success) {
        require(balanceOf[msg.sender] >= value, "Insufficient balance");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        emit Transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) public returns (bool success) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) public returns (bool success) {
        require(balanceOf[from] >= value, "Insufficient balance");
        require(allowance[from][msg.sender] >= value, "Insufficient allowance");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        allowance[from][msg.sender] -= value;
        emit Transfer(from, to, value);
        return true;
    }

    function registerUser() external {
        require(!users[msg.sender].isRegistered, "User already registered");
        users[msg.sender] = User(true, 0, 0);
        emit UserRegistered(msg.sender);
    }

    function registerBuyer(string memory _name, string memory location, string memory additionalInfo) external {
        require(!buyers[msg.sender].isVerified, "Buyer already registered");
        buyers[msg.sender] = Buyer(_name, true, location, additionalInfo);
        emit BuyerRegistered(msg.sender, _name);
    }

    function recycleEWaste(string memory description, uint256 weight) external {
        require(users[msg.sender].isRegistered, "User not registered");
        uint256 eWasteId = _eWasteIdCounter;
        eWastes[eWasteId] = EWaste(msg.sender, description, weight, false, false);
        _eWasteIdCounter++;

        users[msg.sender].recycledAmount += weight;
        users[msg.sender].reputation += 1;

        uint256 reward = weight * 10; // 10 tokens per unit of weight
        _mint(msg.sender, reward);

        emit EWasteRecycled(eWasteId, msg.sender, weight);
    }

    function createErrand(string memory description, uint256 reward) external {
        require(users[msg.sender].isRegistered, "User not registered");
        require(balanceOf[msg.sender] >= reward, "Insufficient balance for reward");

        uint256 errandId = _errandIdCounter;
        errands[errandId] = Errand(address(0), msg.sender, description, reward, false);
        _errandIdCounter++;

        transfer(address(this), reward);

        emit ErrandCreated(errandId, msg.sender, reward);
    }

    function completeErrand(uint256 errandId) external {
        require(users[msg.sender].isRegistered, "User not registered");
        Errand storage errand = errands[errandId];
        require(!errand.isCompleted, "Errand already completed");
        require(errand.runner == address(0), "Errand already assigned");

        errand.runner = msg.sender;
        errand.isCompleted = true;

        transfer(msg.sender, errand.reward);
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
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");

        transfer(recycler, amount);
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

    function getErrandCount() public view returns (uint256) {
        return _errandIdCounter;
    }

    function getErrand(uint256 errandId) public view returns (address, address, string memory, uint256, bool) {
        Errand memory errand = errands[errandId];
        return (errand.runner, errand.creator, errand.description, errand.reward, errand.isCompleted);
    }

    function getEWasteCount() public view returns (uint256) {
        return _eWasteIdCounter;
    }

    function getEWaste(uint256 eWasteId) public view returns (address, string memory, uint256, bool, bool) {
        EWaste memory eWaste = eWastes[eWasteId];
        return (eWaste.recycler, eWaste.description, eWaste.weight, eWaste.isCollected, eWaste.isProcessed);
    }

    function _mint(address account, uint256 amount) internal {
        require(account != address(0), "ERC20: mint to the zero address");
        totalSupply += amount;
        balanceOf[account] += amount;
        emit Transfer(address(0), account, amount);
    }
}