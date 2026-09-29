"""Ground truth equations for the round trip benchmark.

Written the way a person types them in a paper, not tuned to any model.
Each entry is (category, latex).
"""

EQUATIONS: list[tuple[str, str]] = [
    # Fractions
    ("fraction", r"\frac{a+b}{c-d}"),
    ("fraction", r"\frac{1}{1+\frac{1}{x}}"),
    ("fraction", r"\frac{\partial f}{\partial x}"),
    ("fraction", r"\frac{n!}{k!(n-k)!}"),
    ("fraction", r"\frac{dy}{dx}=\frac{y}{x}"),
    ("fraction", r"\frac{x^{2}-1}{x+1}=x-1"),
    ("fraction", r"\sqrt{\frac{a}{b}}"),
    ("fraction", r"\frac{\sin\theta}{\cos\theta}=\tan\theta"),
    # Integrals
    ("integral", r"\int_{0}^{1}x^{2}\,dx=\frac{1}{3}"),
    ("integral", r"\int_{-\infty}^{\infty}e^{-x^{2}}\,dx=\sqrt{\pi}"),
    ("integral", r"\oint_{C}\mathbf{F}\cdot d\mathbf{r}"),
    ("integral", r"\int_{a}^{b}f'(x)\,dx=f(b)-f(a)"),
    ("integral", r"\iint_{D}f(x,y)\,dA"),
    ("integral", r"\int\frac{dx}{x}=\ln|x|+C"),
    ("integral", r"\int_{0}^{\pi}\sin x\,dx=2"),
    ("integral", r"F(\omega)=\int_{-\infty}^{\infty}f(t)e^{-i\omega t}\,dt"),
    # Matrices
    ("matrix", r"\begin{pmatrix}a&b\\c&d\end{pmatrix}"),
    ("matrix", r"\begin{bmatrix}1&0&0\\0&1&0\\0&0&1\end{bmatrix}"),
    ("matrix", r"\det\begin{vmatrix}a&b\\c&d\end{vmatrix}=ad-bc"),
    ("matrix", r"A^{-1}=\frac{1}{ad-bc}\begin{pmatrix}d&-b\\-c&a\end{pmatrix}"),
    ("matrix", r"\begin{pmatrix}x_{1}\\x_{2}\end{pmatrix}"),
    ("matrix", r"\begin{bmatrix}\cos\theta&-\sin\theta\\\sin\theta&\cos\theta\end{bmatrix}"),
    # Sums, products, limits
    ("sum", r"\sum_{i=1}^{n}i=\frac{n(n+1)}{2}"),
    ("sum", r"\sum_{n=0}^{\infty}\frac{x^{n}}{n!}=e^{x}"),
    ("sum", r"\prod_{k=1}^{n}k=n!"),
    ("sum", r"\lim_{x\to0}\frac{\sin x}{x}=1"),
    ("sum", r"\sum_{k=0}^{n}\binom{n}{k}=2^{n}"),
    ("sum", r"\lim_{n\to\infty}\left(1+\frac{1}{n}\right)^{n}=e"),
    ("sum", r"\sum_{i=1}^{n}\sum_{j=1}^{m}a_{ij}"),
    ("sum", r"\zeta(s)=\sum_{n=1}^{\infty}\frac{1}{n^{s}}"),
    # Greek letters and subscripts
    ("greek", r"\alpha+\beta=\gamma"),
    ("greek", r"\Delta x\,\Delta p\geq\frac{\hbar}{2}"),
    ("greek", r"\sigma^{2}=\frac{1}{N}\sum_{i=1}^{N}(x_{i}-\mu)^{2}"),
    ("greek", r"\lambda_{\max}"),
    ("greek", r"x_{n+1}=x_{n}-\frac{f(x_{n})}{f'(x_{n})}"),
    ("greek", r"\nabla\cdot\mathbf{E}=\frac{\rho}{\varepsilon_{0}}"),
    ("greek", r"\Gamma(n)=(n-1)!"),
    ("greek", r"\phi_{t}+\psi_{x}=\omega^{2}"),
    # Mixed and multi-part
    ("mixed", r"E=mc^{2}"),
    ("mixed", r"x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}"),
    ("mixed", r"e^{i\pi}+1=0"),
    ("mixed", r"a^{2}+b^{2}=c^{2}"),
    ("mixed", r"f(x)=\begin{cases}x&x\geq0\\-x&x<0\end{cases}"),
    ("mixed", r"\|x\|_{2}=\sqrt{\sum_{i}x_{i}^{2}}"),
    ("mixed", r"P(A|B)=\frac{P(B|A)P(A)}{P(B)}"),
    ("mixed", r"\mathbb{E}[X]=\sum_{x}x\,p(x)"),
    ("mixed", r"\frac{\partial^{2}u}{\partial t^{2}}=c^{2}\nabla^{2}u"),
    ("mixed", r"\log_{2}(xy)=\log_{2}x+\log_{2}y"),
]
