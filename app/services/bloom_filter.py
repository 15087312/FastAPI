"""布隆过滤器服务 - 用于快速判断商品 ID 是否存在"""

import logging
from typing import Optional
from bloom_filter2 import BloomFilter

logger = logging.getLogger(__name__)

# 布隆过滤器配置
DEFAULT_MAX_ELEMENTS = 1000000  # 最大元素数量
DEFAULT_ERROR_RATE = 0.001     # 误判率 0.1%


class ProductBloomFilter:
    """商品 ID 布隆过滤器"""

    _instance: Optional['ProductBloomFilter'] = None
    _bloom_filter: Optional[BloomFilter] = None
    _initialized = False
    _loaded_count = 0  # 记录已加载的元素数量

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not ProductBloomFilter._initialized:
            self._bloom_filter = BloomFilter(
                max_elements=DEFAULT_MAX_ELEMENTS,
                error_rate=DEFAULT_ERROR_RATE
            )
            ProductBloomFilter._initialized = True
            logger.info(f"布隆过滤器初始化完成，最大元素: {DEFAULT_MAX_ELEMENTS}, 误判率: {DEFAULT_ERROR_RATE}")

    def add(self, product_id: int) -> bool:
        """添加商品 ID 到布隆过滤器"""
        if self._bloom_filter is not None:
            self._bloom_filter.add(product_id)
            ProductBloomFilter._loaded_count += 1
            return True
        return False

    def add_batch(self, product_ids: list) -> int:
        """批量添加商品 ID"""
        if self._bloom_filter is None:
            return 0
        count = 0
        for pid in product_ids:
            self._bloom_filter.add(pid)
            count += 1
        ProductBloomFilter._loaded_count += count
        logger.info(f"批量添加 {count} 个商品 ID 到布隆过滤器")
        return count

    def contains(self, product_id: int) -> bool:
        """检查商品 ID 是否可能存在
        
        Returns:
            True: 可能存在（可能是误判）
            False: 一定不存在
        """
        if self._bloom_filter is None:
            # 如果布隆过滤器未初始化，返回 True 让请求继续查数据库
            return True
        return product_id in self._bloom_filter

    def is_initialized(self) -> bool:
        """检查布隆过滤器是否已加载数据"""
        return ProductBloomFilter._loaded_count > 0

    def get_size(self) -> int:
        """获取已存储的元素数量"""
        return ProductBloomFilter._loaded_count

    def reset(self):
        """重置布隆过滤器"""
        if self._bloom_filter is not None:
            self._bloom_filter = BloomFilter(
                max_elements=DEFAULT_MAX_ELEMENTS,
                error_rate=DEFAULT_ERROR_RATE
            )
            ProductBloomFilter._loaded_count = 0
            logger.info("布隆过滤器已重置")


# 单例实例
product_bloom_filter = ProductBloomFilter()